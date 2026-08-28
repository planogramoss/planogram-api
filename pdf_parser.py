# -*- coding: utf-8 -*-
"""
Planogram PDF Ayristirici
==========================
Murphy USA / QuickChek planogram PDF sablonundan (COOKIES 6FT SET 2026
formati) konum listesini otomatik cikarir. Sutun sayisi sayfadan sayfaya
degisebildigi icin (bos hucrelerin PDF motoru tarafindan birlestirilmesi
nedeniyle), her satirdaki BOS OLMAYAN degerleri sirayla okuyoruz - bu,
mutlak sutun index'ine degil veri sirasina dayandigi icin cok daha
saglamdir. 61 satirlik gercek PDF ile test edilip elle hazirlanan veriyle
%100 dogrulandi.
"""

import re
import io
import pdfplumber


def parse_planogram_pdf(file_bytes: bytes) -> dict:
    """PDF byte icerigini alir, planogram meta bilgisini ve konum
    listesini dondurur.

    Donen sozluk:
        date_live, pog_id: metin (bulunabilirse)
        slots: [{location_id, uin, name, upc, position, size,
                 facing_wide, facing_high, fixture}, ...]
        removed_products: PDF'in "Products Removed" tablosundaki satirlar
    """
    slots = []
    removed_products = []
    seen_locations = set()
    current_fixture = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        first_text = pdf.pages[0].extract_text() or ""
        date_m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", first_text)
        live_m = re.search(r"Live\s+(\d+)", first_text)

        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    clean = [c.strip() if isinstance(c, str) else c for c in row]
                    col1 = clean[1] if len(clean) > 1 else None

                    if col1 and any(
                        c and isinstance(c, str) and c.startswith("Width") for c in clean
                    ):
                        current_fixture = col1
                        continue

                    if col1 == "Location ID":
                        continue

                    if col1 and isinstance(col1, str) and col1.strip().startswith("#"):
                        tokens = [t for t in clean if t not in (None, "")]
                        if len(tokens) < 5:
                            continue
                        loc_id = tokens[0].replace("#", "").strip()
                        if loc_id in seen_locations:
                            continue
                        uin = tokens[1]
                        name = tokens[2]
                        upc = tokens[3]
                        position = tokens[4]
                        size = tokens[5] if len(tokens) > 5 else "0"
                        facing_wide = tokens[6] if len(tokens) > 6 else "1"
                        facing_high = tokens[7] if len(tokens) > 7 else "1"
                        seen_locations.add(loc_id)
                        slots.append(
                            {
                                "location_id": loc_id,
                                "uin": uin,
                                "name": name,
                                "upc": upc,
                                "position": position,
                                "size": size,
                                "facing_wide": int(facing_wide) if str(facing_wide).isdigit() else 1,
                                "facing_high": int(facing_high) if str(facing_high).isdigit() else 1,
                                "fixture": current_fixture,
                            }
                        )

            text = page.extract_text() or ""
            if "Products Removed from Planogram" in text:
                for table in page.extract_tables():
                    if table and table[0] and "UPC" in (table[0][1] or ""):
                        for row in table[1:]:
                            vals = [c for c in row if c]
                            if vals:
                                removed_products.append(vals)

    slots.sort(key=lambda s: int(s["location_id"]))
    return {
        "date_live": date_m.group(1) if date_m else None,
        "pog_id": "Live " + live_m.group(1) if live_m else None,
        "slots": slots,
        "removed_products": removed_products,
    }


def diff_planograms(old_slots: list, new_slots: list) -> dict:
    """Eski ve yeni konum listelerini UPC bazinda karsilastirir.

    Donen sozluk:
        added: yeni planogramda olup eskide olmayan urunler
        removed: eskide olup yeni planogramda olmayan urunler
        moved: her ikisinde de olan ama konumu degisen urunler
               [{upc, name, old_location, new_location}, ...]
        unchanged_count: konumu degismeyen urun sayisi
    """
    old_by_upc = {s["upc"]: s for s in old_slots}
    new_by_upc = {s["upc"]: s for s in new_slots}

    added = [s for upc, s in new_by_upc.items() if upc not in old_by_upc]
    removed = [s for upc, s in old_by_upc.items() if upc not in new_by_upc]

    moved = []
    unchanged_count = 0
    for upc, new_s in new_by_upc.items():
        old_s = old_by_upc.get(upc)
        if old_s is None:
            continue
        if old_s["location_id"] != new_s["location_id"]:
            moved.append(
                {
                    "upc": upc,
                    "name": new_s["name"],
                    "old_location": old_s["location_id"],
                    "old_fixture": old_s["fixture"],
                    "new_location": new_s["location_id"],
                    "new_fixture": new_s["fixture"],
                }
            )
        else:
            unchanged_count += 1

    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "unchanged_count": unchanged_count,
    }
