# ASKİ Su Kesintileri

Ankara'daki su kesintilerini ASKİ'nin sitesinden otomatik okuyup telefonda ve web sayfasında ilçe ilçe gösteren basit bir sistem.

## Mimari

```
ASKİ sayfası (www.aski.gov.tr/tr/Kesinti.aspx)
        │
        │  GitHub Actions (zamanlanmış, hedef: 15 dakikada bir)
        ▼
   scraper.py ──► kesintiler.db    (SQLite: görülen tüm kesintiler, geçmiş)
              ──► kesintiler.json  (şu an sayfada olanlar + son 30 günde bitenler)
        │
        │  liste değiştiyse bot repoya commit atar
        ▼
raw.githubusercontent.com/Deleny/aski-su-kesinti/main/kesintiler.json
        │
        ├──► Expo uygulaması (mobile/App.js) okur ve gösterir
        └──► Streamlit web sayfası (web/app.py) okur ve gösterir
```

Sunucu yok, API yok: GitHub hem zamanlayıcı hem de dosya sunucusu görevini görüyor.

| Dosya | Görevi |
|---|---|
| `scraper.py` | Sayfayı indirir, kartları okur, db ve json dosyalarını günceller. Liste değişmediyse dosyalara dokunmaz. |
| `kesintiler.db` | Tek tablo (`kesintiler`). Sayfadan kalkan kesinti silinmez, `aktif = 0` olur. |
| `kesintiler.json` | `{"guncelleme": "...", "kesintiler": [...], "gecmis": [...]}`. `gecmis`, veritabanındaki son 30 günün biten kesintileri. |
| `.github/workflows/scrape.yml` | Scraper'ı çalıştırır, değişiklik varsa commit edip push eder. |
| `mobile/App.js` | Uygulamanın tamamı: ilçe seçimi, "Şu an / Geçmiş" sekmeleri, son açılıştan beri çıkan kesintilerde "YENİ" etiketi. JSON adresi dosyanın en üstünde. |
| `web/app.py` | Web sayfası (Streamlit): ilçe seçimi, "Şu an / Geçmiş" sekmeleri, yenile butonu. Seçilen ilçe adres çubuğunda (`?ilce=MAMAK`) tutulur. |
| `web/requirements.txt` | Web sayfasının paketleri. Kökteki `requirements.txt`'den ayrı, böylece bot her çalışmada Streamlit kurmaz. |
| `.streamlit/config.toml` | Web sayfasının renkleri. Streamlit Cloud bu dosyanın kökte olmasını istiyor. |

## Nasıl çalıştırılır

Windows PowerShell'de `npx` ve `npm` yerine `npx.cmd` ve `npm.cmd` yaz.

**Scraper (bilgisayarda deneme):**

```bash
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python scraper.py
```

Yerelde çalıştırınca `kesintiler.db` ve `kesintiler.json` değişebilir. Bunları commit etme, bot zaten güncelliyor; geri almak için: `git restore kesintiler.db kesintiler.json`

**Workflow'u elle tetiklemek:** GitHub'da Actions → "ASKİ kesintilerini çek" → Run workflow.

**Mobil uygulama (Expo Go):**

```bash
cd mobile
npm install
npx expo start
```

Telefona Expo Go'yu kur, terminaldeki QR kodu okut (iPhone'da Kamera uygulamasıyla). Telefon ve bilgisayar aynı ağda olmalı.

**Web sayfası (bilgisayarda):**

```bash
.\venv\Scripts\pip install -r web\requirements.txt
.\venv\Scripts\streamlit run web\app.py
```

Tarayıcıda `http://localhost:8501` açılır.

**Web sayfasını internete koymak (Streamlit Community Cloud, ücretsiz):** share.streamlit.io'ya GitHub hesabıyla gir → Create app → repo `Deleny/aski-su-kesinti`, branch `main`, dosya `web/app.py` → Deploy. Bot JSON'u güncelledikçe sayfa da en geç 5 dakika içinde yeni veriyi gösterir; yeniden deploy gerekmez.

**Android APK:**

```bash
cd mobile
npx eas-cli@latest build -p android --profile preview
```

## Git ile çalışırken

Bot da repoya commit attığı için **push etmeden önce mutlaka** şunu çalıştır:

```bash
git pull --rebase
```

Yoksa push "rejected" hatasıyla reddedilir.

## Bilinen sınırlar

- **Veri gecikmeli.** Hedef 15-20 dakikalık gecikme. Ama GitHub zamanlanmış çalışmaları yoğunlukta geciktirip atlayabiliyor: workflow genelde 7 saatte bir çalışıyor; cron dakikalarını kalabalık olmayan dakikalara kaydırmak da düzeltmedi. Üstüne raw.githubusercontent.com dosyayı yaklaşık 5 dakika, web sayfası da 5 dakika önbellekte tutuyor.
- **Web sayfası uykuya geçebilir.** Streamlit Cloud'un ücretsiz planı, bir süre kimse açmayan sayfayı uyutur; açan kişi "uyandır" butonuna basıp yaklaşık bir dakika bekler. Web sayfasında "YENİ" etiketi yok, çünkü sayfa ziyaretçinin en son neyi gördüğünü hatırlamıyor.
- **Bildirim yok.** Uygulamayı açıp bakmak gerekir; açınca son açılıştan beri çıkan kesintiler "YENİ" diye işaretlenir. Gerçek push bildirimi Expo Go'da çalışmıyor; iPhone için ücretli Apple Developer üyeliği, ayrıca telefonların bildirim adreslerini tutacak internette bir veritabanı gerekir.
- **ASKİ sayfa yapısını değiştirirse scraper güncellenmeli.** Bu durumda Actions'taki çalışmalar kırmızı olur ve dosyalar eski hâliyle kalır.
- **Okunamayan tek bir kart atlanır.** Actions'ta uyarı olarak görünür, o kesinti uygulamada çıkmaz.
- **İlçe adları sabit listeyle eşleşmeli.** Türkçe harfsiz yazımlar ("SEREFLIKOÇHISAR" gibi) otomatik düzeltiliyor; listede hiç olmayan bir ad gelirse o kesinti sadece "Tümü"de görünür.
- **ASKİ detay metnini değiştirirse kesinti yeni sayılır.** `id`, ilçe + arıza tarihi + detay metninden üretiliyor; metin değişince eski kayıt geçmişe düşer, yenisi "YENİ" etiketiyle görünür.
- Tarih ve saatler Türkiye saatidir.
