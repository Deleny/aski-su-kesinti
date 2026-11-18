"""ASKİ (Ankara) su kesintisi sayfasını okur.

Geçmişi kesintiler.db (SQLite) dosyasında, güncel listeyi kesintiler.json
dosyasında tutar. Liste değişmediyse dosyalara hiç dokunmaz.
"""

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ADRES = "https://www.aski.gov.tr/tr/Kesinti.aspx"
ZAMAN_ASIMI = 30  # saniye; site cevap vermezse sonsuza kadar beklemeyelim
BASLIKLAR = {
    # Bazı siteler tarayıcı gibi görünmeyen istekleri reddeder
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}
# Her kartta bulunması gereken alanlar (sayfadaki kalın yazılı etiketler)
ETIKETLER = ["Arıza Tarihi", "Tamir Tarihi", "Detay", "Etkilenen Yerler"]

# Dosyalar, komut nereden çalıştırılırsa çalıştırılsın scraper.py'nin yanında dursun
KLASOR = Path(__file__).parent
DB_DOSYASI = KLASOR / "kesintiler.db"
JSON_DOSYASI = KLASOR / "kesintiler.json"

# GitHub'ın sunucuları UTC saatiyle çalışır; biz zamanı Türkiye saatiyle yazıyoruz
TURKIYE_SAATI = timezone(timedelta(hours=3))

# Uygulamada "Geçmiş" listesinde son kaç günün biten kesintileri gösterilsin.
# Veritabanı hepsini saklar; bu sadece JSON dosyası şişmesin diye.
GECMIS_GUN = 30


def bosluk_temizle(metin):
    """Satır sonlarını ve art arda gelen boşlukları tek boşluğa indirir."""
    return " ".join(metin.split())


def turkce_harfsiz(metin):
    """Büyük Türkçe harfleri İngilizce karşılıklarına çevirir: ŞİŞLİ -> SISLI."""
    return metin.translate(str.maketrans("ÇĞİÖŞÜ", "CGIOSU"))


# Ankara'nın 25 ilçesi, doğru yazılışlarıyla (mobil uygulamadaki listeyle aynı).
# ASKİ bazen ilçe adını Türkçe harfsiz yazıyor ("SEREFLIKOÇHISAR" gibi);
# harfsiz hâlinden doğru yazılışa giden bir sözlük kuruyoruz.
ILCELER = [
    "AKYURT", "ALTINDAĞ", "AYAŞ", "BALA", "BEYPAZARI",
    "ÇAMLIDERE", "ÇANKAYA", "ÇUBUK", "ELMADAĞ", "ETİMESGUT",
    "EVREN", "GÖLBAŞI", "GÜDÜL", "HAYMANA", "KAHRAMANKAZAN",
    "KALECİK", "KEÇİÖREN", "KIZILCAHAMAM", "MAMAK", "NALLIHAN",
    "POLATLI", "PURSAKLAR", "SİNCAN", "ŞEREFLİKOÇHİSAR", "YENİMAHALLE",
]
DOGRU_YAZILIS = {turkce_harfsiz(ilce): ilce for ilce in ILCELER}


def ilce_normalize(metin):
    """İlçe adını Türkçe kurallarına göre büyük harfe çevirir.

    Python'un upper() fonksiyonu Türkçe bilmez: "i" harfini "I" yapar
    ("çubuk" doğru çıkar ama "sincan" -> "SINCAN" olur). Bu yüzden önce
    i -> İ ve ı -> I çevirisini elle yapıp sonra upper() çağırıyoruz.
    Sonra ad 25 ilçeden birine benziyorsa onun doğru yazılışını kullanıyoruz.
    """
    metin = bosluk_temizle(metin)
    buyuk = metin.replace("i", "İ").replace("ı", "I").upper()
    # Listede yoksa (yeni ya da bilinmeyen bir ad) olduğu gibi bırak
    return DOGRU_YAZILIS.get(turkce_harfsiz(buyuk), buyuk)


def tarih_cevir(metin):
    """'7.11.2026 09:40:00' -> '2026-11-07T09:40:00' (ISO formatı)."""
    return datetime.strptime(metin, "%d.%m.%Y %H:%M:%S").isoformat()


def kimlik_uret(ilce, ariza_tarihi, detay):
    """Kesintiye ilçe + arıza tarihi + detay üzerinden sabit bir id üretir.

    Aynı kesinti her okunduğunda aynı id çıkar; böylece veritabanına
    ikinci kez eklenmez. SHA-256 özetinin ilk 16 karakteri yeterli.
    """
    metin = ilce + "|" + ariza_tarihi + "|" + detay
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()[:16]


def sayfayi_indir():
    """ASKİ sayfasının HTML'ini döndürür. Sorun olursa requests hata fırlatır."""
    yanit = requests.get(ADRES, headers=BASLIKLAR, timeout=ZAMAN_ASIMI)
    yanit.raise_for_status()  # 404, 500 gibi cevaplarda hata fırlatır
    yanit.encoding = "utf-8"  # Türkçe karakterler bozulmasın
    return yanit.text


def alanlari_oku(paragraf):
    """Karttaki <p> içinden 'etiket -> değer' sözlüğü çıkarır.

    Sayfadaki yapı şöyle:
        <b>Arıza Tarihi: </b>15.11.2026 12:40:00<br />
        <b>Tamir Tarihi: </b>15.11.2026 18:00:00<br />
    Yani değer, <b> etiketinden sonra gelen ve bir sonraki <b>'ye kadar
    süren düz metindir.
    """
    alanlar = {}
    for b in paragraf.find_all("b"):
        etiket = b.get_text().strip().rstrip(":").strip()
        parcalar = []
        for kardes in b.next_siblings:
            if isinstance(kardes, str):  # düz metin
                parcalar.append(kardes)
            elif kardes.name == "b":  # sonraki etikete geldik, dur
                break
            else:  # <br> gibi başka bir etiket
                parcalar.append(kardes.get_text(" "))
        alanlar[etiket] = bosluk_temizle(" ".join(parcalar))
    return alanlar


def kesintileri_ayikla(html):
    """HTML'den kesinti listesini çıkarır.

    Kesinti yoksa boş liste döndürür.
    Sayfa beklediğimiz yapıda değilse ValueError fırlatır.
    """
    sayfa = BeautifulSoup(html, "html.parser")

    # Doğru sayfada mıyız? Bu başlık yoksa ya engellendik ya da yapı değişti.
    if sayfa.select_one("#LblMenuBaslik") is None:
        raise ValueError("sayfa başlığı (#LblMenuBaslik) bulunamadı")

    # Her kesinti <ul class="history"> içindeki bir <li> kartıdır
    kartlar = sayfa.select("ul.history > li")

    if not kartlar:
        # Kart bulamadık ama sayfada "Arıza Tarihi" yazıyorsa kesinti var
        # demektir; yani kartların HTML yapısı değişmiş, biz göremiyoruz.
        if "Arıza Tarihi" in sayfa.get_text():
            raise ValueError("kesinti var ama kartlar (ul.history > li) bulunamadı")
        return []  # gerçekten kesinti yok

    kesintiler = []
    gorulen_idler = set()
    hatali_kartlar = []
    for sira, kart in enumerate(kartlar, start=1):
        try:
            kesinti = karti_oku(kart)
        except ValueError as hata:
            # Tek bir garip kart yüzünden bütün listeyi kaybetmeyelim:
            # bu kartı atla, uyarı yaz, diğerleriyle devam et.
            hatali_kartlar.append(f"{sira}. kart: {hata}")
            continue

        if kesinti["id"] in gorulen_idler:
            continue  # aynı kart sayfada iki kez varsa birini al
        gorulen_idler.add(kesinti["id"])
        kesintiler.append(kesinti)

    for aciklama in hatali_kartlar:
        # "::warning::" ile başlayan satır GitHub Actions'ta uyarı olarak görünür
        print(f"::warning::Kart atlandı ({aciklama})")

    # Kart var ama hiçbiri okunamadıysa sayfa yapısı gerçekten değişmiş demektir
    if hatali_kartlar and not kesintiler:
        raise ValueError(f"{len(kartlar)} kartın hiçbiri okunamadı; "
                         f"ilk hata: {hatali_kartlar[0]}")
    return kesintiler


def karti_oku(kart):
    """Tek bir kesinti kartını sözlüğe çevirir.

    Kart beklenen yapıda değilse ValueError fırlatır.
    """
    # İlk kalın başlık ilçe, ikincisi kaynak ("Arıza Kaynaklı" gibi)
    basliklar = kart.select("h4 strong")
    paragraf = kart.select_one("p")
    if len(basliklar) < 2 or paragraf is None:
        raise ValueError("kartın içinde başlıklar ya da paragraf yok")

    alanlar = alanlari_oku(paragraf)
    for etiket in ETIKETLER:
        if etiket not in alanlar:
            raise ValueError(f"kartta '{etiket}' alanı yok")

    ilce = ilce_normalize(basliklar[0].get_text())
    ariza_tarihi = tarih_cevir(alanlar["Arıza Tarihi"])  # bozuksa ValueError
    detay = alanlar["Detay"]
    # Tamir tarihi boş bırakılmış olabilir; arıza tarihi ise zorunlu
    tamir = alanlar["Tamir Tarihi"]

    return {
        "id": kimlik_uret(ilce, ariza_tarihi, detay),
        "ilce": ilce,
        "kaynak": bosluk_temizle(basliklar[1].get_text()),
        "ariza_tarihi": ariza_tarihi,
        "tamir_tarihi": tarih_cevir(tamir) if tamir else None,
        "detay": detay,
        # Sayfada bu alan "; Cengizhan mahallesi..." diye başlıyor
        "etkilenen_yerler": alanlar["Etkilenen Yerler"].lstrip("; "),
    }


def onceki_listeyi_oku():
    """Bir önceki çalışmada kesintiler.json'a yazılan listeyi döndürür.

    Dosyalardan biri eksikse (ilk çalıştırma) None döndürür.
    """
    if not JSON_DOSYASI.exists() or not DB_DOSYASI.exists():
        return None
    veri = json.loads(JSON_DOSYASI.read_text(encoding="utf-8"))
    # Eski biçimde (geçmiş listesi olmadan) yazılmışsa bir kez yeniden yazılsın
    if "gecmis" not in veri:
        return None
    return veri["kesintiler"]


def veritabanini_guncelle(kesintiler, simdi):
    """Geçmişi tutan SQLite tablosunu sayfadaki listeye göre günceller."""
    baglanti = sqlite3.connect(DB_DOSYASI)
    baglanti.execute("""
        CREATE TABLE IF NOT EXISTS kesintiler (
            id               TEXT PRIMARY KEY,
            ilce             TEXT,
            kaynak           TEXT,
            ariza_tarihi     TEXT,
            tamir_tarihi     TEXT,
            detay            TEXT,
            etkilenen_yerler TEXT,
            ilk_gorulme      TEXT,
            aktif            INTEGER
        )
    """)

    # Önce hepsini pasif yap; sayfada olanları aşağıda tekrar aktif yapacağız.
    # Böylece sayfadan kalkan kesinti silinmez, aktif=0 olarak geçmişte kalır.
    baglanti.execute("UPDATE kesintiler SET aktif = 0")

    for kesinti in kesintiler:
        # Yeni kesintiyse ekle. id zaten varsa "OR IGNORE" sayesinde
        # hiçbir şey olmaz, yani aynı kesinti ikinci kez eklenmez.
        baglanti.execute(
            """INSERT OR IGNORE INTO kesintiler
               VALUES (:id, :ilce, :kaynak, :ariza_tarihi, :tamir_tarihi,
                       :detay, :etkilenen_yerler, :ilk_gorulme, 1)""",
            {**kesinti, "ilk_gorulme": simdi},
        )
        # Zaten kayıtlıysa aktif yap ve değişmiş olabilecek alanları güncelle
        # (ASKİ tamir saatini uzatabiliyor). ilk_gorulme'ye dokunmuyoruz.
        baglanti.execute(
            """UPDATE kesintiler
               SET kaynak = :kaynak, tamir_tarihi = :tamir_tarihi,
                   etkilenen_yerler = :etkilenen_yerler, aktif = 1
               WHERE id = :id""",
            kesinti,
        )

    baglanti.commit()
    baglanti.close()


def gecmisi_oku():
    """Son GECMIS_GUN gün içinde başlamış ve artık sayfada olmayan kesintileri
    veritabanından okur, en yeniden eskiye sıralı döndürür."""
    sinir = (datetime.now(TURKIYE_SAATI) - timedelta(days=GECMIS_GUN))
    # Veritabanındaki tarihler "2026-11-15T12:40:00" biçiminde (saat dilimi yok);
    # aynı biçimde yazınca metin olarak karşılaştırmak tarih karşılaştırması olur.
    sinir = sinir.strftime("%Y-%m-%dT%H:%M:%S")

    baglanti = sqlite3.connect(DB_DOSYASI)
    baglanti.row_factory = sqlite3.Row  # satırları sözlük gibi okuyabilmek için
    satirlar = baglanti.execute(
        """SELECT id, ilce, kaynak, ariza_tarihi, tamir_tarihi, detay, etkilenen_yerler
           FROM kesintiler
           WHERE aktif = 0 AND ariza_tarihi >= ?
           ORDER BY ariza_tarihi DESC""",
        (sinir,),
    ).fetchall()
    baglanti.close()

    gecmis = []
    for satir in satirlar:
        kesinti = dict(satir)
        # Eski kayıtlarda ilçe adı hatalı yazılmış olabilir; gösterirken düzelt
        kesinti["ilce"] = ilce_normalize(kesinti["ilce"])
        gecmis.append(kesinti)
    return gecmis


def json_yaz(kesintiler, gecmis, simdi):
    """Mobil uygulamanın okuyacağı dosyayı yazar: güncel liste ve geçmiş."""
    veri = {"guncelleme": simdi, "kesintiler": kesintiler, "gecmis": gecmis}
    # ensure_ascii=False: Türkçe harfler ı gibi kodlanmasın, okunaklı kalsın
    metin = json.dumps(veri, ensure_ascii=False, indent=2) + "\n"
    # newline="\n": Windows'ta da Linux'ta da aynı dosya çıksın
    JSON_DOSYASI.write_text(metin, encoding="utf-8", newline="\n")


def main():
    # 1) Sayfayı indir
    try:
        html = sayfayi_indir()
    except requests.RequestException as hata:
        print(f"HATA: ASKİ sayfası indirilemedi: {hata}")
        sys.exit(1)

    # 2) Kesintileri ayıkla
    try:
        kesintiler = kesintileri_ayikla(html)
    except ValueError as hata:
        print(f"HATA: Sayfa yapısı tanınmadı: {hata}")
        sys.exit(1)

    print(f"Sayfada {len(kesintiler)} kesinti var.")
    for kesinti in kesintiler:
        print(f"  {kesinti['ilce']} - {kesinti['ariza_tarihi']}")

    # 3) Liste bir öncekiyle aynıysa dosyalara hiç dokunma (gereksiz commit olmasın)
    if kesintiler == onceki_listeyi_oku():
        print("Değişiklik yok, dosyalara dokunulmadı.")
        return

    # 4) Değişiklik var: veritabanını ve JSON'u güncelle
    simdi = datetime.now(TURKIYE_SAATI).isoformat(timespec="seconds")
    veritabanini_guncelle(kesintiler, simdi)
    json_yaz(kesintiler, gecmisi_oku(), simdi)
    print("Liste değişti: kesintiler.db ve kesintiler.json güncellendi.")


if __name__ == "__main__":
    main()
