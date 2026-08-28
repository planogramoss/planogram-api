
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
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from seed_data import PLANOGRAM_META, PRODUCTS, SLOTS

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
            """
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

        return result


# ---------------------------------------------------------------------------
# Endpointler
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Planogram Scan API",
        "planogram": PLANOGRAM_META,
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
        rows = db.execute(
            """SELECT ps.location_id, ps.active, l.fixture, l.position,
                      l.facing_wide, l.facing_high, p.upc, p.name, p.size
               FROM planogram_slots ps
               JOIN locations l ON l.location_id = ps.location_id
               LEFT JOIN products p ON p.upc = ps.upc
               ORDER BY CAST(ps.location_id AS INTEGER)"""
        ).fetchall()
    return {
        "meta": PLANOGRAM_META,
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
        db.execute(
            "INSERT INTO audit_sessions (session_id, store_id, started_at, planogram_version) "
            "VALUES (?,?,?,?)",
            (session_id, req.store_id, datetime.utcnow().isoformat(), PLANOGRAM_META["version"]),
        )
    return {"session_id": session_id, "planogram_version": PLANOGRAM_META["version"]}


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
