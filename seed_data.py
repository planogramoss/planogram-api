# -*- coding: utf-8 -*-
"""
COOKIES 6FT SET 2026 - Murphy USA / QuickChek planogram verisi.
Kaynak: COOKIES_6FT_SET_2026.pdf (Live 79781, Date Last Modified 7/30/2026)

Bu dosya API'nin baslangic (seed) verisidir. Planogram guncellendiginde
(yeni bir PDF geldiginde) SLOTS listesini yeniden olusturup import edebilirsiniz.
Alternatif olarak /api/admin/import-planogram uctan JSON ile de guncellenebilir.
"""

PLANOGRAM_META = {
    "name": "COOKIES 6FT SET 2026",
    "pog_id": "Live 79781",
    "date_live": "2025-03-03",
    "date_last_modified": "2026-07-30",
    "version": "79781-2026-07-30",
}

FIXTURES = [
    {"fixture": "Pegboard 5", "width_in": 72.00, "height_in": 37.00, "depth_in": 0.10, "merch_height_in": 8.00},
    {"fixture": "Shelf 4", "width_in": 72.00, "height_in": 32.00, "depth_in": 16.00, "merch_height_in": 4.00},
    {"fixture": "Shelf 3", "width_in": 72.00, "height_in": 25.00, "depth_in": 17.00, "merch_height_in": 6.00},
    {"fixture": "Shelf 2", "width_in": 72.00, "height_in": 16.50, "depth_in": 17.00, "merch_height_in": 1.00},
    {"fixture": "Shelf 1", "width_in": 72.00, "height_in": 6.00, "depth_in": 19.00, "merch_height_in": 11.00},
]

# location_id, uin, name, upc, position, size, facing_wide, facing_high, fixture
_RAW_SLOTS = [
    # Pegboard 5
    ("1", "5005201", "OREO SNDWCH COOK CHOC MINI", "4400000680", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("2", "500512", "CHIPS AHOY COOK MINI", "4400000679", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("3", "524813", "FAMOUS AMOS CKIE CHOC CHIP", "7667705908", "Front", "0", 1, 1, "Pegboard 5"),
    ("4", "5134961", "REESES ANIMAL CRACKERS DIPPED", "3400021753", "Front", "4 OZ", 1, 1, "Pegboard 5"),
    ("5", "415572", "GOLDFISH SNACK CRACKER CHEDDAR", "1410004552", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("6", "6829061", "CHEEZ-IT GRB N GO SNCK CRKR ORIG", "2410019134", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("7", "479623", "CHEEZE-IT BK SNCK CRCKR XTR-TSTY", "2410011626", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("8", "5317991", "NAB OREO PB MINI BIG BAG 3OZ", "4400008179", "Front", "0", 1, 1, "Pegboard 5"),
    ("9", "007260", "PILLSBURY MINI C-CHIP", "1800051068", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("10", "427077", "NAB CH AHOY CHEWY MINI 12/3 Z", "4400004736", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("11", "453698", "MEIJI PANDA CHOC BAG", "7232070076", "Front", "2 OZ", 1, 1, "Pegboard 5"),
    ("12", "1522721", "NUTTER BUTTER BTS SNDWCH COOK PB", "4400000306", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("13", "540578", "PALMER CAKE POP BDAY CAKE POPPRS", "7723215314", "Front", "0", 1, 1, "Pegboard 5"),
    ("14", "5004621", "RITZ BITS CRACKER SANDWICHES CHS", "4400000677", "Front", "3 OZ", 1, 1, "Pegboard 5"),
    ("15", "483237", "CHEEZ-IT BK SNCK CRCKR EXTR CHSY", "2410011773", "Front", "3 OZ", 1, 1, "Pegboard 5"),

    # Shelf 4
    ("16", "508628", "LNL VANILLA COMPLETE CREME 2.9OZ", "78769272506", "Front", "0", 1, 1, "Shelf 4"),
    ("17", "422029", "LENNY & LARRYS CMPLTE CKIE MACADAMIA", "78769283834", "Front", "0", 1, 1, "Shelf 4"),
    ("18", "460663", "LNL PEANUTBUTTER CHOC CHIP COOKIE 4OZ", "78769283541", "Front", "0", 1, 1, "Shelf 4"),
    ("19", "444372", "LENNY & LARRYS CMPLTE CKIE CHC CHP", "78769283461", "Front", "0", 1, 1, "Shelf 4"),
    ("20", "455549", "QUEST PRTN COOK C-CHP", "88884900599", "Front", "2 OZ", 1, 1, "Shelf 4"),
    ("21", "526001", "QUEST STRBRY FRSTD CKIE 7.05OZ", "88884901453", "Front", "0", 1, 1, "Shelf 4"),
    ("22", "514127", "QUEST COOKIE CHOC CAKE 7.05OZ", "88884901221", "Front", "0", 1, 1, "Shelf 4"),
    ("23", "536062", "MCD STRWBERY TOASTER PASTRY PROTEIN 4OZ", "85006910461", "Front", "0", 1, 1, "Shelf 4"),
    ("24", "536070", "MCD MILK & COOKIES PROTEIN 4OZ", "85006910459", "Front", "0", 1, 1, "Shelf 4"),
    ("25", "545203", "MCD CHOC GANACHE PROTEIN 4.3OZ", "85006910463", "Front", "0", 1, 1, "Shelf 4"),
    ("26", "496329", "HONEY STINGR WAFFLE HONEY", "81081502103", "Front", "0", 1, 1, "Shelf 4"),
    ("27", "496327", "HONEY STINGR WAFFLE GF SLTD CRML", "81081502137", "Front", "0", 1, 1, "Shelf 4"),
    ("28", "533969", "RITZ CRACKER SANDWICH P-BTR", "4400000210", "Front", "1 OZ", 1, 1, "Shelf 4"),
    ("29", "814830", "KEEBLER SNDWCH CRCKR TST/P-BTR", "3010012518", "Turned", "2 OZ", 1, 1, "Shelf 4"),

    # Shelf 3
    ("30", "505178", "NAB CAKESTERS OREO ORIG", "4400006991", "Front", "3 OZ", 1, 1, "Shelf 3"),
    ("31", "533389", "NAB OREO KING SIZE", "4400008208", "Front", "0", 1, 1, "Shelf 3"),
    ("32", "533390", "NAB OREO DBL STUFF KS NEW 4.15 OZ", "4400008211", "Front", "4 OZ", 1, 1, "Shelf 3"),
    ("33", "533388", "NAB OREO DBL STUFF GLDN KS NEW 4.15 OZ", "4400008214", "Front", "0", 1, 1, "Shelf 3"),
    ("34", "444197", "NUTTER BUTTER KING SIZE", "4400003658", "Front", "4 OZ", 1, 1, "Shelf 3"),
    ("35", "456196", "NAB CHIPS AHOY ORIG KS", "4400005694", "Front", "4 OZ", 1, 1, "Shelf 3"),
    ("36", "530302", "NAB CHIPS AHOY BIG CHEWY ORIG 2.5OZ", "4400008017", "Front", "0", 1, 1, "Shelf 3"),
    ("37", "513957", "NUTELLA B READY 2PK", "980082002", "Front", "2 OZ", 1, 1, "Shelf 3"),
    ("38", "814814", "KEEBLER SNDWCH CRCKRS CLB/CHDDR", "3010012521", "Turned", "2 OZ", 1, 1, "Shelf 3"),
    ("39", "814822", "KEEBLER SNDWCH CRCKR CHS/P-BTR", "3010012515", "Turned", "2 OZ", 1, 1, "Shelf 3"),

    # Shelf 2
    ("40", "532750", "NAB OREO CKIE LOADED", "4400008159", "Front", "0", 1, 1, "Shelf 2"),
    ("41", "548069", "NAB OREO CAKESTER GOLDEN", "4400008059", "Front", "0", 1, 1, "Shelf 2"),
    ("42", "492225", "DUNKAROOS VAN COOK/FROST/SPRNKLS", "1600028801", "Front", "2 OZ", 1, 1, "Shelf 2"),
    ("43", "509186", "KEEBLER CKIE SFT BTCH CHOC CHIP 2.2 OZ", "2780006270", "Front", "2 OZ", 1, 1, "Shelf 2"),
    ("44", "518138", "KEEBLER CKIE SGR WAFER STRW KS", "2780007357", "Front", "4 OZ", 1, 1, "Shelf 2"),
    ("45", "518139", "KEEBLER CKIE SGR WAFER VAN KS", "2780007356", "Front", "4 OZ", 1, 1, "Shelf 2"),
    ("46", "530743", "POCKY STRAWBERRY BISCUIT STICKS 1.41OZ", "7314115005", "Front", "0", 1, 1, "Shelf 2"),
    ("47", "530751", "GLICO POCKY CHOC 1.41OZ", "7314115004", "Front", "0", 1, 1, "Shelf 2"),
    ("48", "425546", "LOACKER WAFER CLSC HZLNUT", "7658016017", "Front", "0", 1, 1, "Shelf 2"),
    ("49", "062182", "NUTELLA/GO SPREAD HAZELNUT", "980080005", "Front", "2 OZ", 1, 1, "Shelf 2"),
    ("50", "472271", "DAELMANS WAFER JMBO DBL C", "85375400305", "Front", "3 OZ", 1, 1, "Shelf 2"),
    ("51", "439294", "CAKEBITES CLASSIC ITAL RAINBOW", "3769516034", "Front", "2 OZ", 1, 1, "Shelf 2"),

    # Shelf 1
    ("52", "519094", "NAB OREO CKIE", "4400006011", "Turned", "13 OZ", 1, 1, "Shelf 1"),
    ("53", "5190951", "NAB OREO DBL STUFF 14.03OZ", "4400006013", "Turned", "0", 1, 1, "Shelf 1"),
    ("54", "4362791", "NAB CHIPS AHOY CHEWY 13OZ", "4400003223", "Turned", "0", 1, 1, "Shelf 1"),
    ("55", "4363861", "NAB CH AHOY ORIG", "4400003219", "Front", "13 OZ", 1, 1, "Shelf 1"),
    ("56", "453697", "MEIJI PANDA CHOC", "7232070091", "Front", "7 OZ", 1, 1, "Shelf 1"),
    ("57", "5091821", "KBLR FDG STRPS 11.5OZ", "2780006570", "Front", "0", 1, 1, "Shelf 1"),
    ("58", "040352", "PREMIUM SALTINE ORIG", "4400000382", "Front", "4 OZ", 1, 1, "Shelf 1"),
    ("59", "4335201", "GOLDFISH BK SNCK CRKR CHDR", "1410008547", "Front", "7 OZ", 1, 1, "Shelf 1"),
    ("60", "7949581", "NAB RITZ CRACKER ORIG 10.3OZ", "4400003112", "Front", "0", 1, 1, "Shelf 1"),
    ("61", "533622", "NEWTONS FRUIT CHEWY COOKIES FIG", "4400003744", "Front", "2 OZ", 1, 1, "Shelf 1"),
]

SLOTS = [
    {
        "location_id": r[0],
        "uin": r[1],
        "name": r[2],
        "upc": r[3],
        "position": r[4],
        "size": r[5],
        "facing_wide": r[6],
        "facing_high": r[7],
        "fixture": r[8],
    }
    for r in _RAW_SLOTS
]

# Urun master listesini konum listesinden turet (ayni UPC birden fazla
# konuma atanmis olabilir; ilk gorulen isim/boyut kullanilir).
_seen = set()
PRODUCTS = []
for s in SLOTS:
    if s["upc"] not in _seen:
        _seen.add(s["upc"])
        PRODUCTS.append({"upc": s["upc"], "uin": s["uin"], "name": s["name"], "size": s["size"]})

# PDF'in "Products Removed from Planogram" tablosu bos (Count of Removed = 0).
# Ileride bir urun planogramdan kaldirilirsa buraya eklenip
# planogram_slots.active = 0 yapilabilir; API bunu otomatik islemek icin hazir.
REMOVED_PRODUCTS = []

# Urun fotograflari (opsiyonel). UPC -> resim URL'si veya /images/xxx.jpg gibi
# yerel bir dosya yolu. Bos birakilirsa uygulama otomatik olarak generic bir
# paket ikonu gosterir. Magaza kendi cektigi urun fotograflarini buraya
# ekleyebilir, mevcut sistemin geri kalanini degistirmeye gerek yok.
PRODUCT_IMAGES = {
    # "4400000680": "https://ornek-adres.com/oreo-mini.jpg",
}

