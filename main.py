# -*- coding: utf-8 -*-
"""
Planogram Scan API
===================
Telefonla bir urunun uzerindeki UPC/PDI numarasi taratildiginda:
  1) Urunun aktif planogramda kayitli olup olmadigini kontrol eder,
  2) Dogru rafini / peg konumunu bulur,
  3) Eger tarama sirasinda bir konum (location_id) da belirtilirse,
     o konumda GERCEKTE olmasi gereken urunle taranan urunu karsilastirir,
  4) Uyusmazlik varsa: o konumda olmasi gereken urunun ne oldugunu ve
     taranan urunun asil dogru yerinin neresi oldugunu doner,
  5) Tam raf sayimi (audit) modunda ise raftaki tum taramalari planogramla
     karsilastirip MISSING / MISPLACED / OK statuleri ve olasi "yer degistirme"
     (swap) tespitini raporlar - yani bir urun yerinden alinip baska yere
     konulmussa, acikta kalan / yerinden edilen urun de raporda gorunur.

Calistirma:
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Swagger UI / interaktif test: http://localhost:8000/docs
"""

from __future__ import annotations

import sqlite3
import uuid
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from seed_data import PLANOGRAM_META, PRODUCTS, SLOTS, PRODUCT_IMAGES
from pdf_parser import parse_planogram_pdf, diff_planograms

DB_PATH = Path(__file__).parent / "planogram.db"

app = FastAPI(
    title="Planogram Scan API",
    description="UPC/PDI tarama ile planogram konum dogrulama ve raf sayim servisi",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------

def normalize_code(code: str) -> str:
    """UPC/PDI karsilastirmasi icin normallestirme: bosluk temizle,
    bastaki sifirlari at (12 haneli GTIN ile 10 haneli PDI kodunun
    kolayca eslesebilmesi icin)."""
    if code is None:
        return ""
    c = code.strip().replace(" ", "").replace("-", "")
    stripped = c.lstrip("0")
    return stripped or "0"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(reset: bool = False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                upc TEXT PRIMARY KEY,
                upc_norm TEXT,
                uin TEXT,
                name TEXT NOT NULL,
                size TEXT
            );

            CREATE TABLE IF NOT EXISTS locations (
                location_id TEXT PRIMARY KEY,
                fixture TEXT NOT NULL,
                position TEXT,
                facing_wide INTEGER DEFAULT 1,
                facing_high INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS planogram_slots (
                location_id TEXT PRIMARY KEY REFERENCES locations(location_id),
                upc TEXT REFERENCES products(upc),
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS audit_sessions (
                session_id TEXT PRIMARY KEY,
                store_id TEXT,
                started_at TEXT,
                planogram_version TEXT
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES audit_sessions(session_id),
                location_id TEXT,
                upc_raw TEXT,
                scanned_at TEXT,
                result TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_products_norm ON products(upc_norm);
            CREATE INDEX IF NOT EXISTS idx_scanlog_session ON scan_log(session_id);

            CREATE TABLE IF NOT EXISTS planogram_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_uploads (
                id TEXT PRIMARY KEY,
                slots_json TEXT,
                meta_json TEXT,
                diff_json TEXT,
                created_at TEXT
            );
            """
        )

        meta_seeded = db.execute("SELECT COUNT(*) c FROM planogram_meta").fetchone()["c"]
        if meta_seeded == 0:
            for k, v in PLANOGRAM_META.items():
                db.execute(
                    "INSERT OR IGNORE INTO planogram_meta (key, value) VALUES (?,?)", (k, str(v))
                )

        seeded = db.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        if seeded == 0:
            for p in PRODUCTS:
                db.execute(
                    "INSERT OR IGNORE INTO products (upc, upc_norm, uin, name, size) VALUES (?,?,?,?,?)",
                    (p["upc"], normalize_code(p["upc"]), p["uin"], p["name"], p["size"]),
                )
            for s in SLOTS:
                db.execute(
                    "INSERT OR IGNORE INTO locations "
                    "(location_id, fixture, position, facing_wide, facing_high) VALUES (?,?,?,?,?)",
                    (s["location_id"], s["fixture"], s["position"], s["facing_wide"], s["facing_high"]),
                )
                db.execute(
                    "INSERT OR IGNORE INTO planogram_slots (location_id, upc, active) VALUES (?,?,1)",
                    (s["location_id"], s["upc"]),
                )


def get_current_meta(db) -> dict:
    rows = db.execute("SELECT key, value FROM planogram_meta").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_current_slots_flat(db) -> list:
    """Su anki aktif planogramin duz listesini (diff icin) dondurur."""
    rows = db.execute(
        """SELECT ps.location_id, p.upc, p.name, l.fixture
           FROM planogram_slots ps
           JOIN locations l ON l.location_id = ps.location_id
           LEFT JOIN products p ON p.upc = ps.upc
           WHERE ps.active = 1"""
    ).fetchall()
    return [dict(r) for r in rows if r["upc"]]


def reseed_from_slots(db, new_slots: list, meta: dict):
    """Veritabanini TAMAMEN yeni bir konum listesiyle degistirir.
    Yeni bir PDF onaylandiginda kullanilir. Eski scan_log / audit_sessions
    gecmisi korunur, sadece urun/konum/planogram_slots tablolari
    yeni veriyle degistirilir."""
    db.execute("DELETE FROM planogram_slots")
    db.execute("DELETE FROM locations")
    db.execute("DELETE FROM products")

    seen = set()
    for s in new_slots:
        if s["upc"] not in seen:
            seen.add(s["upc"])
            db.execute(
                "INSERT OR IGNORE INTO products (upc, upc_norm, uin, name, size) VALUES (?,?,?,?,?)",
                (s["upc"], normalize_code(s["upc"]), s.get("uin"), s["name"], s.get("size")),
            )
    for s in new_slots:
        db.execute(
            "INSERT OR IGNORE INTO locations "
            "(location_id, fixture, position, facing_wide, facing_high) VALUES (?,?,?,?,?)",
            (
                s["location_id"],
                s["fixture"],
                s.get("position"),
                s.get("facing_wide", 1),
                s.get("facing_high", 1),
            ),
        )
        db.execute(
            "INSERT OR IGNORE INTO planogram_slots (location_id, upc, active) VALUES (?,?,1)",
            (s["location_id"], s["upc"]),
        )

    for k, v in meta.items():
        db.execute(
            "INSERT INTO planogram_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)),
        )


init_db()


def find_product(db, upc_raw: str):
    norm = normalize_code(upc_raw)
    return db.execute(
        "SELECT * FROM products WHERE upc = ? OR upc_norm = ? LIMIT 1",
        (upc_raw, norm),
    ).fetchone()


def expected_slot(db, location_id: str):
    return db.execute(
        """SELECT ps.location_id, ps.upc, ps.active, p.name, p.size, l.fixture
           FROM planogram_slots ps
           LEFT JOIN products p ON p.upc = ps.upc
           LEFT JOIN locations l ON l.location_id = ps.location_id
           WHERE ps.location_id = ?""",
        (location_id,),
    ).fetchone()


def correct_locations_for_upc(db, upc: str):
    return db.execute(
        """SELECT ps.location_id, l.fixture, l.position
           FROM planogram_slots ps
           JOIN locations l ON l.location_id = ps.location_id
           WHERE ps.upc = ? AND ps.active = 1""",
        (upc,),
    ).fetchall()


def get_shelf_context(db, location_id: str):
    """Verilen konumun rafta nerede oldugunu (fixture, o fixture icindeki
    sira/toplam) ve sol-sag komsu urunlerini dondurur. Gorsel harita ve
    komsu urun kartlari icin kullanilir."""
    slot = db.execute(
        """SELECT ps.location_id, ps.upc, l.fixture
           FROM planogram_slots ps JOIN locations l ON l.location_id = ps.location_id
           WHERE ps.location_id = ?""",
        (location_id,),
    ).fetchone()
    if slot is None:
        return None

    fixture_rows = db.execute(
        """SELECT ps.location_id, ps.upc, p.name, p.upc as pupc
           FROM planogram_slots ps LEFT JOIN products p ON p.upc = ps.upc
           JOIN locations l ON l.location_id = ps.location_id
           WHERE l.fixture = ? AND ps.active = 1
           ORDER BY CAST(ps.location_id AS INTEGER)""",
        (slot["fixture"],),
    ).fetchall()

    ids = [r["location_id"] for r in fixture_rows]
    idx = ids.index(location_id)

    def _neighbor(i):
        if i < 0 or i >= len(fixture_rows):
            return None
        r = fixture_rows[i]
        return {
            "location_id": r["location_id"],
            "upc": r["pupc"],
            "name": r["name"],
            "image_url": PRODUCT_IMAGES.get(r["pupc"] or "", None),
        }

    return {
        "location_id": location_id,
        "fixture": slot["fixture"],
        "position_index": idx + 1,
        "fixture_total": len(fixture_rows),
        "left_neighbor": _neighbor(idx - 1),
        "right_neighbor": _neighbor(idx + 1),
        "image_url": PRODUCT_IMAGES.get(slot["upc"] or "", None),
    }


# ---------------------------------------------------------------------------
# Pydantic semalari
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    upc: str = Field(..., description="Taranan UPC / PDI numarasi")
    location_id: Optional[str] = Field(
        None, description="Urunun bulundugu raf/peg etiket numarasi (opsiyonel ama onerilir)"
    )
    session_id: Optional[str] = Field(
        None, description="Devam eden bir raf sayim (audit) oturumu varsa ID'si"
    )


class AuditStartRequest(BaseModel):
    store_id: Optional[str] = Field(None, description="Magaza / lokasyon kodu")


class AuditScanRequest(BaseModel):
    location_id: str
    upc: str


# ---------------------------------------------------------------------------
# Cekirdek is mantigi (endpoint disinda tutulur, hem /scan hem /audit kullanir)
# ---------------------------------------------------------------------------

def do_scan(req: ScanRequest) -> dict:
    with get_db() as db:
        product = find_product(db, req.upc)

        result: dict = {
            "scanned_upc": req.upc,
            "product_found": product is not None,
            "product": None,
            "active_in_planogram": False,
            "correct_locations": [],
            "location_check": None,
            "message": "",
        }

        if product is None:
            result["message"] = (
                "Bu UPC/PDI numarasi sistemde kayitli degil - planogramda tanimli bir urun bulunamadi."
            )
        else:
            result["product"] = {
                "upc": product["upc"],
                "uin": product["uin"],
                "name": product["name"],
                "size": product["size"],
            }
            locs = correct_locations_for_upc(db, product["upc"])
            result["active_in_planogram"] = len(locs) > 0
            result["correct_locations"] = [
                {"location_id": r["location_id"], "fixture": r["fixture"], "position": r["position"]}
                for r in locs
            ]
            result["message"] = (
                "Urun aktif planogramda kayitli."
                if locs
                else "Urun tanimli ancak aktif planogramda bir konuma atanmamis (kaldirilmis olabilir)."
            )

        if req.location_id:
            slot = expected_slot(db, req.location_id)
            if slot is None:
                result["location_check"] = {
                    "status": "unknown_location",
                    "location_id": req.location_id,
                    "message": f"'{req.location_id}' planogramda tanimli bir konum degil.",
                }
            else:
                expected_upc = slot["upc"]
                is_match = (
                    product is not None
                    and expected_upc
                    and normalize_code(expected_upc) == normalize_code(product["upc"])
                )
                if is_match:
                    result["location_check"] = {
                        "status": "match",
                        "location_id": req.location_id,
                        "fixture": slot["fixture"],
                        "message": "Urun dogru konumda.",
                    }
                else:
                    expected_info = (
                        {"upc": expected_upc, "name": slot["name"], "size": slot["size"]}
                        if expected_upc
                        else None
                    )
                    check = {
                        "status": "mismatch",
                        "location_id": req.location_id,
                        "fixture": slot["fixture"],
                        "expected_product": expected_info,
                        "scanned_product": result["product"],
                    }
                    if product:
                        own_locs = result["correct_locations"]
                        if own_locs:
                            where = ", ".join(l["location_id"] for l in own_locs)
                            check["message"] = (
                                f"Bu konumda '{slot['name'] or expected_upc}' olmasi gerekiyor, "
                                f"ama taranan urun farkli. Taranan urunun ({product['name']}) "
                                f"planogramdaki dogru yeri: {where}."
                            )
                        else:
                            check["message"] = (
                                f"Bu konumda '{slot['name'] or expected_upc}' olmasi gerekiyor, "
                                f"ama taranan urun ({product['name']}) aktif planogramda hicbir "
                                f"konuma atanmamis - yabanci/raf disi urun olabilir."
                            )
                    else:
                        check["message"] = (
                            f"Bu konumda '{slot['name'] or expected_upc}' olmasi gerekiyor, "
                            f"ama taranan kod sistemde hic tanimli degil - yabanci urun olabilir."
                        )
                    result["location_check"] = check

        if req.session_id:
            status = (result["location_check"] or {}).get("status", "scanned")
            db.execute(
                "INSERT INTO scan_log (session_id, location_id, upc_raw, scanned_at, result) "
                "VALUES (?,?,?,?,?)",
                (req.session_id, req.location_id, req.upc, datetime.utcnow().isoformat(), status),
            )

        # --- Gorsel harita verisi ---------------------------------------
        # "target": urunun planogramdaki dogru yerinin raf-icindeki konumu
        # ve sol/sag komsulari. "wrong": eger uyusmazlik varsa, urunun
        # YANLIS bulundugu konumun raf-icindeki konumu (kirmizi isaretleme
        # icin). Ikisi ayni fixture'daysa tek serit, degilse iki ayri
        # serit olarak gosterilir.
        visual = None
        if result["correct_locations"]:
            target_loc = result["correct_locations"][0]["location_id"]
            target_ctx = get_shelf_context(db, target_loc)
            visual = {"target": target_ctx, "wrong": None}
            lc = result["location_check"]
            if lc and lc.get("status") == "mismatch":
                wrong_ctx = get_shelf_context(db, lc["location_id"])
                if wrong_ctx:
                    visual["wrong"] = {
                        "location_id": wrong_ctx["location_id"],
                        "fixture": wrong_ctx["fixture"],
                        "position_index": wrong_ctx["position_index"],
                        "fixture_total": wrong_ctx["fixture_total"],
                    }
        result["visual"] = visual

        return result


# ---------------------------------------------------------------------------
# Endpointler
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    with get_db() as db:
        meta = get_current_meta(db)
    return {
        "service": "Planogram Scan API",
        "planogram": meta,
        "docs": "/docs",
        "scanner": "/scanner",
    }


@app.get("/scanner")
def scanner_page():
    """Telefon kamerasiyla barkod tarama demo sayfasi.
    API ile ayni adresten sunulur, boylece ngrok/https uzerinden
    tek bir link paylasmak yeterli olur."""
    return FileResponse(Path(__file__).parent / "demo" / "scanner.html")


@app.get("/api/planogram")
def get_planogram():
    """Tum aktif planogramin duz listesi (fixture, konum, urun)."""
    with get_db() as db:
        meta = get_current_meta(db)
        rows = db.execute(
            """SELECT ps.location_id, ps.active, l.fixture, l.position,
                      l.facing_wide, l.facing_high, p.upc, p.name, p.size
               FROM planogram_slots ps
               JOIN locations l ON l.location_id = ps.location_id
               LEFT JOIN products p ON p.upc = ps.upc
               ORDER BY CAST(ps.location_id AS INTEGER)"""
        ).fetchall()
    return {
        "meta": meta,
        "slots": [dict(r) for r in rows],
    }


@app.get("/api/products/{upc}")
def get_product(upc: str):
    with get_db() as db:
        product = find_product(db, upc)
        if not product:
            raise HTTPException(404, "Urun bulunamadi")
        locs = correct_locations_for_upc(db, product["upc"])
    return {
        "product": dict(product),
        "correct_locations": [dict(r) for r in locs],
        "active_in_planogram": len(locs) > 0,
    }


@app.post("/api/scan")
def scan(req: ScanRequest):
    """Tek bir urun taramasi. Sadece UPC verilirse urun/konum bilgisini dondurur.
    location_id de verilirse, o konumdaki beklenen urunle karsilastirir."""
    return do_scan(req)


@app.post("/api/audit/start")
def audit_start(req: AuditStartRequest):
    session_id = uuid.uuid4().hex[:12]
    with get_db() as db:
        meta = get_current_meta(db)
        version = meta.get("version", "unknown")
        db.execute(
            "INSERT INTO audit_sessions (session_id, store_id, started_at, planogram_version) "
            "VALUES (?,?,?,?)",
            (session_id, req.store_id, datetime.utcnow().isoformat(), version),
        )
    return {"session_id": session_id, "planogram_version": version}


@app.post("/api/audit/{session_id}/scan")
def audit_scan(session_id: str, req: AuditScanRequest):
    """Raf sayimi sirasinda tek bir taramayi kaydeder ve o an icin
    konum/urun uyusmazligini da geri doner (aninda uyari icin)."""
    with get_db() as db:
        session = db.execute(
            "SELECT 1 FROM audit_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Sayim oturumu bulunamadi")
    scan_req = ScanRequest(upc=req.upc, location_id=req.location_id, session_id=session_id)
    return do_scan(scan_req)


@app.get("/api/audit/{session_id}/report")
def audit_report(session_id: str):
    """Sayim oturumunun tam raporu: her konum icin OK / MISSING / MISPLACED,
    ve yer degistirmis (swap) urunlerin eslestirmesi."""
    with get_db() as db:
        session = db.execute(
            "SELECT * FROM audit_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Sayim oturumu bulunamadi")

        # Her konum icin en son taramayi al (bir konum birden fazla kez
        # taranmis olabilir - sonuncusu gecerli sayilir)
        scans = db.execute(
            """SELECT location_id, upc_raw, MAX(scanned_at) ts
               FROM scan_log
               WHERE session_id=? AND location_id IS NOT NULL
               GROUP BY location_id""",
            (session_id,),
        ).fetchall()
        scanned_map = {r["location_id"]: r["upc_raw"] for r in scans}

        all_slots = db.execute(
            """SELECT ps.location_id, ps.upc expected_upc, p.name expected_name
               FROM planogram_slots ps
               LEFT JOIN products p ON p.upc = ps.upc
               WHERE ps.active = 1
               ORDER BY CAST(ps.location_id AS INTEGER)"""
        ).fetchall()

        report = []
        for slot in all_slots:
            loc = slot["location_id"]
            expected = slot["expected_upc"]
            scanned = scanned_map.get(loc)

            if scanned is None:
                report.append({
                    "location_id": loc,
                    "status": "MISSING",
                    "expected": {"upc": expected, "name": slot["expected_name"]},
                    "found": None,
                })
            elif expected and normalize_code(scanned) == normalize_code(expected):
                report.append({
                    "location_id": loc,
                    "status": "OK",
                    "expected": {"upc": expected, "name": slot["expected_name"]},
                    "found": {"upc": scanned},
                })
            else:
                found_product = find_product(db, scanned)
                report.append({
                    "location_id": loc,
                    "status": "MISPLACED",
                    "expected": {"upc": expected, "name": slot["expected_name"]},
                    "found": {
                        "upc": scanned,
                        "name": found_product["name"] if found_product else None,
                        "known_product": found_product is not None,
                    },
                })

        # --- Yer degistirme (swap) tespiti ---------------------------------
        # Bir konumda (MISPLACED) bulunan urun, planogramda BASKA bir konumun
        # "olmasi gereken" (expected) urunuyle ayniysa, o urun oradan buraya
        # tasinmis demektir. Bu, hem klasik "A yerinde degil / bulunamadi"
        # (MISSING) durumunu hem de iki urunun birbirinin yerine gectigi tam
        # swap durumunu (her iki konum da MISPLACED gorunur) yakalar.
        expected_by_upc: dict = {}
        for r in report:
            exp_upc = r["expected"]["upc"]
            if exp_upc:
                expected_by_upc.setdefault(normalize_code(exp_upc), []).append(r["location_id"])

        swaps = []
        seen_pairs = set()
        for r in report:
            if r["status"] == "MISPLACED" and r["found"]["upc"]:
                key = normalize_code(r["found"]["upc"])
                origin_candidates = [loc for loc in expected_by_upc.get(key, []) if loc != r["location_id"]]
                if origin_candidates:
                    origin_loc = origin_candidates[0]
                    r["note"] = f"Bu urun aslinda '{origin_loc}' konumundan buraya tasinmis olabilir."
                    pair_key = tuple(sorted([origin_loc, r["location_id"]])) + (r["found"]["upc"],)
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        swaps.append({
                            "product_upc": r["found"]["upc"],
                            "product_name": r["found"]["name"],
                            "moved_from": origin_loc,
                            "moved_to": r["location_id"],
                        })

        summary = {
            "total_slots": len(report),
            "ok": sum(1 for r in report if r["status"] == "OK"),
            "missing": sum(1 for r in report if r["status"] == "MISSING"),
            "misplaced": sum(1 for r in report if r["status"] == "MISPLACED"),
            "detected_swaps": len(swaps),
        }

        return {
            "session_id": session_id,
            "store_id": session["store_id"],
            "planogram_version": session["planogram_version"],
            "summary": summary,
            "details": report,
            "swaps": swaps,
        }


@app.post("/api/admin/reset")
def admin_reset():
    """Gelistirme/test amacli: veritabanini seed_data.py'daki verilerle sifirdan kurar."""
    init_db(reset=True)
    return {"status": "reset_ok"}


# ---------------------------------------------------------------------------
# Planogram guncelleme (yeni PDF yukleme + karsilastirma + onaylama)
# ---------------------------------------------------------------------------

@app.post("/api/admin/upload-planogram")
async def upload_planogram(file: UploadFile = File(...)):
    """Yeni bir planogram PDF'i yukler, otomatik olarak konum listesini
    cikarir ve MEVCUT aktif planogramla karsilastirir. Hicbir sey
    DEGISTIRMEZ - sadece fark raporu doner. Kullanici raporu onaylarsa
    /api/admin/apply-planogram cagrilir."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Sadece PDF dosyasi yuklenebilir.")

    content = await file.read()
    try:
        parsed = parse_planogram_pdf(content)
    except Exception as e:
        raise HTTPException(400, f"PDF okunamadi: {e}")

    if not parsed["slots"]:
        raise HTTPException(
            400,
            "PDF'ten hicbir konum verisi cikarilamadi. Dosyanin Murphy USA / "
            "QuickChek planogram sablonuna uygun oldugundan emin olun.",
        )

    with get_db() as db:
        old_slots = get_current_slots_flat(db)
        diff = diff_planograms(old_slots, parsed["slots"])

        pending_id = uuid.uuid4().hex[:10]
        new_meta = {
            "name": parsed.get("pog_id") or "Guncellenmis Planogram",
            "pog_id": parsed.get("pog_id") or "",
            "date_live": parsed.get("date_live") or "",
            "date_last_modified": datetime.utcnow().strftime("%Y-%m-%d"),
            "version": f"upload-{pending_id}",
        }
        db.execute(
            "INSERT INTO pending_uploads (id, slots_json, meta_json, diff_json, created_at) "
            "VALUES (?,?,?,?,?)",
            (
                pending_id,
                json.dumps(parsed["slots"]),
                json.dumps(new_meta),
                json.dumps(diff),
                datetime.utcnow().isoformat(),
            ),
        )

    return {
        "pending_id": pending_id,
        "new_total_locations": len(parsed["slots"]),
        "old_total_locations": len(old_slots),
        "diff": diff,
    }


class ApplyPlanogramRequest(BaseModel):
    pending_id: str


@app.post("/api/admin/apply-planogram")
def apply_planogram(req: ApplyPlanogramRequest):
    """Daha once yuklenip incelenen (pending) bir planogramin ONAYLANMASI:
    veritabanini kalici olarak yeni planogramla degistirir."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM pending_uploads WHERE id=?", (req.pending_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Bekleyen yukleme bulunamadi (suresi gecmis olabilir).")

        new_slots = json.loads(row["slots_json"])
        new_meta = json.loads(row["meta_json"])
        reseed_from_slots(db, new_slots, new_meta)
        db.execute("DELETE FROM pending_uploads WHERE id=?", (req.pending_id,))

    return {"status": "applied", "total_locations": len(new_slots), "meta": new_meta}
