# ASKİ su kesintilerinin web sayfası (Streamlit).
# Mobil uygulamayla aynı kesintiler.json dosyasını GitHub'dan okur.
# Çalıştırmak için: .\venv\Scripts\streamlit.exe run web\app.py
import requests
import streamlit as st

# Bot bu dosyayı GitHub'da güncelliyor (mobil uygulamadaki adresle aynı)
JSON_ADRESI = "https://raw.githubusercontent.com/Deleny/aski-su-kesinti/main/kesintiler.json"

# "Tümü" ve Ankara'nın 25 ilçesi; scraper'ın yazdığı adlarla birebir aynı
ILCELER = [
    "Tümü",
    "AKYURT", "ALTINDAĞ", "AYAŞ", "BALA", "BEYPAZARI",
    "ÇAMLIDERE", "ÇANKAYA", "ÇUBUK", "ELMADAĞ", "ETİMESGUT",
    "EVREN", "GÖLBAŞI", "GÜDÜL", "HAYMANA", "KAHRAMANKAZAN",
    "KALECİK", "KEÇİÖREN", "KIZILCAHAMAM", "MAMAK", "NALLIHAN",
    "POLATLI", "PURSAKLAR", "SİNCAN", "ŞEREFLİKOÇHİSAR", "YENİMAHALLE",
]


@st.cache_data(ttl=300)  # 5 dakika boyunca tekrar indirmeden aynı veriyi kullan
def veriyi_getir():
    """kesintiler.json dosyasını indirir. Sorun olursa hata fırlatır."""
    yanit = requests.get(JSON_ADRESI, timeout=20)
    yanit.raise_for_status()
    return yanit.json()


def tarih_yaz(iso):
    """'2026-11-15T12:40:00' -> '15.11.2026 12:40' (mobil uygulamadaki gibi)."""
    if not iso:
        return "Belirtilmemiş"
    tarih, saat = iso.split("T")
    yil, ay, gun = tarih.split("-")
    return f"{gun}.{ay}.{yil} {saat[:5]}"


def duz_metin(metin):
    """ASKİ'nin metnindeki *, _, $ gibi işaretler Streamlit'te biçim
    (kalın yazı, formül vb.) sanılmasın diye önlerine ters bölü koyar."""
    for isaret in "\\`*_$#[]<>~|":
        metin = metin.replace(isaret, "\\" + isaret)
    return metin


def kesinti_karti(kesinti):
    """Tek bir kesintiyi çerçeveli bir kutu içinde gösterir."""
    with st.container(border=True):
        st.markdown(f"#### {kesinti['ilce']}")
        st.caption(duz_metin(kesinti["kaynak"]))

        # İki satır; sonundaki iki boşluk + \n Markdown'da satır atlatır.
        # (Sütun kullanmadık: telefonda Streamlit sütunları alt alta dizip yer kaplıyor.)
        st.markdown(f"**Arıza:** {tarih_yaz(kesinti['ariza_tarihi'])}  \n"
                    f"**Tahmini tamir:** {tarih_yaz(kesinti['tamir_tarihi'])}")

        st.caption("Etkilenen yerler")
        st.markdown(duz_metin(kesinti["etkilenen_yerler"]))
        st.caption("Detay")
        st.markdown(duz_metin(kesinti["detay"]))


def liste_goster(kesintiler, bos_mesaj):
    """Kesinti listesini ya da liste boşsa bilgi mesajını gösterir."""
    if not kesintiler:
        st.info(bos_mesaj)
    for kesinti in kesintiler:
        kesinti_karti(kesinti)


st.set_page_config(page_title="ASKİ Su Kesintileri", page_icon="💧")
# Streamlit'in sayfa üstündeki büyük boşluğunu küçült (GES projesindeki gibi)
st.html("<style>[data-testid='stMainBlockContainer'] { padding-top: 2.5rem; }</style>")
st.title("ASKİ Su Kesintileri")

# --- Veriyi indir; olmazsa hata mesajı ve tekrar dene butonu ---
try:
    veri = veriyi_getir()
except (requests.RequestException, ValueError):
    st.error("Veriler alınamadı. İnternet bağlantını kontrol edip tekrar dene.")
    if st.button("Tekrar dene"):
        st.cache_data.clear()
        st.rerun()
    st.stop()  # sayfanın geri kalanını çizme

# --- İlçe seçimi ---
# Seçilen ilçe adres çubuğunda (?ilce=MAMAK) tutulur; sayfayı yer imine
# eklersen ya da linki paylaşırsan aynı ilçe açılır.
kayitli_ilce = st.query_params.get("ilce", "Tümü")
if kayitli_ilce not in ILCELER:
    kayitli_ilce = "Tümü"

sol, sag = st.columns([3, 1], vertical_alignment="bottom")
ilce = sol.selectbox("İlçe", ILCELER, index=ILCELER.index(kayitli_ilce))
st.query_params["ilce"] = ilce
if sag.button("Yenile", use_container_width=True):
    st.cache_data.clear()  # 5 dakikayı beklemeden GitHub'dan yeniden indir
    st.rerun()

st.caption(f"Liste son değişti: {tarih_yaz(veri.get('guncelleme'))}")


def ilceye_gore(liste):
    """Listeyi seçili ilçeye göre süzer."""
    if ilce == "Tümü":
        return liste
    return [kesinti for kesinti in liste if kesinti["ilce"] == ilce]


su_anki = ilceye_gore(veri["kesintiler"])
# Eski biçimdeki dosyada geçmiş olmayabilir; o zaman boş liste
biten = ilceye_gore(veri.get("gecmis", []))

# --- Şu an / Geçmiş sekmeleri ---
sekme_simdi, sekme_gecmis = st.tabs([f"Şu an ({len(su_anki)})", f"Geçmiş ({len(biten)})"])
with sekme_simdi:
    liste_goster(su_anki, "Şu an kesinti yok." if ilce == "Tümü" else "Bu ilçede kesinti yok.")
with sekme_gecmis:
    liste_goster(biten, "Son 30 günde biten kesinti yok." if ilce == "Tümü"
                 else "Bu ilçede son 30 günde biten kesinti yok.")

st.caption("Veriler ASKİ'nin sitesinden otomatik alınıyor ve gecikmeli olabilir. "
           "Güncel resmî bilgi için: [aski.gov.tr](https://www.aski.gov.tr/tr/Kesinti.aspx)")
