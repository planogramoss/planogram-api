# Planogram Scan API — COOKIES 6FT SET 2026

Telefonla bir ürünün üzerindeki **UPC / PDI numarasını** taratarak:

1. Ürünün aktif planogramda kayıtlı olup olmadığını kontrol eder,
2. Ürünün planogramdaki **doğru rafını / peg konumunu** bulur,
3. Tarama sırasında bulunduğu **konum da belirtilirse**, o konumda
   gerçekte olması gereken ürünle karşılaştırır (doğru yerde mi?),
4. Uyuşmazlık varsa: o konumda olması gereken ürünü ve taranan ürünün
   asıl doğru yerini birlikte döner,
5. Tam **raf sayımı (audit)** modunda, bütün raf taranınca:
   `OK / MISSING (eksik) / MISPLACED (yanlış yerde)` durumlarını ve
   ürünlerin **yer değiştirmesini (swap)** otomatik tespit eder — yani bir
   ürün yerinden alınıp başka yere konulduğunda, açığa çıkan/yerinden
   edilen diğer ürün de raporda görünür.

Veri kaynağı: `COOKIES_6FT_SET_2026.pdf` (Live 79781, son güncelleme 30.07.2026),
`seed_data.py` içine 61 konumluk tam planogram olarak işlendi.

---

## Kurulum

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI (interaktif test): **http://localhost:8000/docs**

İlk çalıştırmada `planogram.db` (SQLite) otomatik oluşturulur ve
`seed_data.py` içindeki veriyle doldurulur.

---

## Uç Noktalar (Endpoints)

| Metot | Yol | Açıklama |
|---|---|---|
| GET | `/api/planogram` | Tüm aktif planogram listesi (61 konum) |
| GET | `/api/products/{upc}` | Tek ürün bilgisi + doğru konumu |
| POST | `/api/scan` | **Tekli tarama** — ürün ve/veya konum kontrolü |
| POST | `/api/audit/start` | Yeni raf sayım oturumu başlatır |
| POST | `/api/audit/{session_id}/scan` | Sayım sırasında tek bir taramayı kaydeder |
| GET | `/api/audit/{session_id}/report` | Tam sayım raporu + swap tespiti |
| POST | `/api/admin/reset` | (Geliştirme) Veritabanını sıfırdan kurar |

### 1) Tekli tarama — sadece ürünü kontrol et

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"upc": "4400000680"}'
```

Döner: ürün bulundu mu, aktif planogramda mı, doğru konum(lar)ı neresi.

### 2) Tekli tarama — ürün + bulunduğu konum

Telefon hem ürünün barkodunu hem de üzerinde bulunduğu raf/peg etiketini
(konum kodunu) okuduğunda kullanılır:

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"upc": "4400000680", "location_id": "2"}'
```

Eğer bu ürün aslında `#1` konumuna aitse, cevapta:

```json
"location_check": {
  "status": "mismatch",
  "location_id": "2",
  "expected_product": {"upc": "4400000679", "name": "CHIPS AHOY COOK MINI"},
  "scanned_product": {"upc": "4400000680", "name": "OREO SNDWCH COOK CHOC MINI"},
  "message": "Bu konumda 'CHIPS AHOY COOK MINI' olmasi gerekiyor, ama taranan urun farkli. Taranan urunun (OREO SNDWCH COOK CHOC MINI) planogramdaki dogru yeri: 1."
}
```

şeklinde hem **o an orada olması gereken ürünü** hem de **taranan ürünün
gerçek yerini** aynı anda görürsünüz.

### 3) Tam raf sayımı + yer değiştirme (swap) tespiti

```bash
# Oturum başlat
curl -X POST http://localhost:8000/api/audit/start -d '{}' \
  -H "Content-Type: application/json"
# -> {"session_id": "abc123..."}

# Rafı tek tek tara (her konum için)
curl -X POST http://localhost:8000/api/audit/abc123/scan \
  -H "Content-Type: application/json" -d '{"location_id":"1","upc":"4400000679"}'
curl -X POST http://localhost:8000/api/audit/abc123/scan \
  -H "Content-Type: application/json" -d '{"location_id":"2","upc":"4400000680"}'
# ... rafın geri kalanı

# Raporu al
curl http://localhost:8000/api/audit/abc123/report
```

Eğer 1 numaralı konumda aslında 2'nin ürünü, 2'de de 1'in ürünü bulunmuşsa
(iki ürün yer değiştirmiş), rapor bunu otomatik olarak yakalar:

```json
"swaps": [
  {"product_upc": "4400000679", "product_name": "CHIPS AHOY COOK MINI", "moved_from": "2", "moved_to": "1"},
  {"product_upc": "4400000680", "product_name": "OREO SNDWCH COOK CHOC MINI", "moved_from": "1", "moved_to": "2"}
]
```

Taranmayan konumlar `MISSING`, planogramda kayıtlı olmayan bir kod
taranırsa `MISPLACED` + `known_product: false` (yabancı/raf dışı ürün)
olarak işaretlenir.

---

## Telefonla Barkod Tarama Demosu

`demo/scanner.html` dosyası kamera erişimiyle barkod okuyan, sonuçları
Türkçe gösteren bağımsız bir sayfadır (`html5-qrcode` kütüphanesi CDN'den
yüklenir, ekstra kurulum gerekmez).

Kullanım:
1. API'yi çalıştırın (`uvicorn main:app ...`).
2. `demo/scanner.html` dosyasını bir tarayıcıda açın (ör. basit bir
   statik sunucuyla: `python3 -m http.server 8080` → `http://<bilgisayar-ip>:8080/scanner.html`).
3. Üstteki **API Adresi** kutusuna sunucunuzun adresini yazın
   (telefon ile bilgisayar aynı ağda olmalı, örn. `http://192.168.1.20:8000`).
4. "📷 Kamerayla Tara" ile barkodu okutun; "Tekli Kontrol" sekmesinde anında
   doğru/yanlış konum bilgisini, "Raf Sayımı" sekmesinde ise tüm rafı tarayıp
   toplu rapor + yer değiştirme tespiti alabilirsiniz.

> **Önemli:** Tarayıcılar kamera erişimine yalnızca **HTTPS** veya
> **localhost** üzerinden izin verir. Gerçek telefon testinde sayfayı
> HTTPS üzerinden servis eden bir ortama (örn. Netlify, Vercel, ngrok)
> koymanız gerekir; API tarafında da CORS zaten açık bırakılmıştır.

---

## Önemli Not: UPC / PDI Kod Farkı

PDF'teki "UPC" sütunu aslında **PDI iç ürün kodu**dur (10 haneli), ürün
paketi üzerindeki gerçek **UPC-A/GTIN-12** barkodundan farklı olabilir.
Gerçek ortamda telefon kamerası paket üzerindeki 12+ haneli barkodu
okuyacağı için:

- API, karşılaştırma yaparken baştaki sıfırları atarak (`normalize_code`)
  esnek eşleştirme yapar, ama **kod tabanları tamamen farklıysa eşleşme
  bulunamaz**.
- En sağlıklı çözüm: gerçek GTIN-12/13 barkod numaralarını içeren bir
  eşleştirme (crosswalk) tablosu çıkarıp `seed_data.py` içindeki `upc`
  alanlarını bu gerçek barkodlarla güncellemektir. Bu veri genelde
  tedarikçi/GS1 kataloğunda ya da mağaza POS sisteminde mevcuttur.

---

## Planogram Güncellemesi

Murphy USA/QuickChek her yeni PDF gönderdiğinde (`Date Last Modified`
değiştiğinde), `seed_data.py` içindeki `SLOTS` listesini yeni PDF'teki
tabloya göre güncelleyip `POST /api/admin/reset` ile veritabanını
yeniden kurabilirsiniz. "Products Removed from Planogram" tablosundaki
ürünler varsa, ilgili `planogram_slots.active` alanı `0` yapılarak
"artık burada olmaması gereken ama hâlâ rafta olabilecek" ürünler de
takip edilebilir hale getirilebilir (kod buna hazırdır).

---

## Proje Yapısı

```
planogram-api/
├── main.py            # FastAPI uygulaması ve tüm endpoint'ler
├── seed_data.py        # PDF'ten çıkarılan planogram verisi (61 konum)
├── requirements.txt
├── demo/
│   └── scanner.html    # Telefon kamerası ile tarama demo sayfası
└── README.md
```
