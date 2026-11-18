import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Platform,
  Pressable,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Kesinti listesinin okunduğu adres (GitHub'daki repodan gelir)
const JSON_ADRESI =
  'https://raw.githubusercontent.com/Deleny/aski-su-kesinti/main/kesintiler.json';

// Seçilen ilçenin telefonda saklandığı anahtar
const ILCE_ANAHTARI = 'secilenIlce';

// Son açılışta görülen kesintilerin id'lerinin saklandığı anahtar ("YENİ" etiketi için)
const GORULEN_ANAHTARI = 'gorulenKesintiler';

// "Tümü" ve Ankara'nın 25 ilçesi. Yazılış, scraper'ın ürettiği
// ilçe adlarıyla (Türkçe büyük harf) birebir aynı olmalı.
const ILCELER = [
  'Tümü',
  'AKYURT', 'ALTINDAĞ', 'AYAŞ', 'BALA', 'BEYPAZARI',
  'ÇAMLIDERE', 'ÇANKAYA', 'ÇUBUK', 'ELMADAĞ', 'ETİMESGUT',
  'EVREN', 'GÖLBAŞI', 'GÜDÜL', 'HAYMANA', 'KAHRAMANKAZAN',
  'KALECİK', 'KEÇİÖREN', 'KIZILCAHAMAM', 'MAMAK', 'NALLIHAN',
  'POLATLI', 'PURSAKLAR', 'SİNCAN', 'ŞEREFLİKOÇHİSAR', 'YENİMAHALLE',
];

// Başlığın saat/pil çubuğunun altında kalmaması için üstten bırakılan boşluk.
// Android bu yüksekliği veriyor; iOS vermediği için sabit bir değer kullanıyoruz.
const UST_BOSLUK = Platform.OS === 'ios' ? 56 : StatusBar.currentHeight;

// "2026-11-15T12:40:00" -> "15.11.2026 12:40"
// Bilerek Date kullanmıyoruz: saatler zaten Türkiye saati, telefonun
// saat dilimine göre kaymasın diye metni parçalayıp yeniden diziyoruz.
function tarihYaz(iso) {
  if (!iso) return 'Belirtilmemiş';
  const [tarih, saat] = iso.split('T');
  const [yil, ay, gun] = tarih.split('-');
  return `${gun}.${ay}.${yil} ${saat.slice(0, 5)}`;
}

// Tek bir kesintiyi gösteren kart. "yeni" doğruysa ilçe adının yanında etiket çıkar.
function KesintiKarti({ kesinti, yeni }) {
  return (
    <View style={styles.kart}>
      <View style={styles.kartUst}>
        <Text style={styles.kartIlce}>{kesinti.ilce}</Text>
        {yeni && <Text style={styles.yeniEtiketi}>YENİ</Text>}
      </View>
      <Text style={styles.kartKaynak}>{kesinti.kaynak}</Text>

      <View style={styles.saatSatiri}>
        <View style={styles.saatKutusu}>
          <Text style={styles.etiket}>Arıza</Text>
          <Text style={styles.saat}>{tarihYaz(kesinti.ariza_tarihi)}</Text>
        </View>
        <View style={styles.saatKutusu}>
          <Text style={styles.etiket}>Tahmini tamir</Text>
          <Text style={styles.saat}>{tarihYaz(kesinti.tamir_tarihi)}</Text>
        </View>
      </View>

      <Text style={styles.etiket}>Etkilenen yerler</Text>
      <Text style={styles.metin}>{kesinti.etkilenen_yerler}</Text>

      <Text style={styles.etiket}>Detay</Text>
      <Text style={styles.metin}>{kesinti.detay}</Text>
    </View>
  );
}

export default function App() {
  const [kesintiler, setKesintiler] = useState([]); // şu an süren kesintiler
  const [gecmis, setGecmis] = useState([]); // son 30 günde biten kesintiler
  const [sekme, setSekme] = useState('simdi'); // 'simdi' ya da 'gecmis'
  const [yeniIdler, setYeniIdler] = useState([]); // son açılıştan beri çıkanlar
  const [guncelleme, setGuncelleme] = useState(null);
  const [yukleniyor, setYukleniyor] = useState(true); // ilk açılış
  const [yenileniyor, setYenileniyor] = useState(false); // aşağı çekme
  const [hata, setHata] = useState(false);
  const [secilenIlce, setSecilenIlce] = useState('Tümü');
  const [modalAcik, setModalAcik] = useState(false);

  // JSON'u internetten indirir. Başarısız olursa hata durumuna geçer.
  async function veriyiGetir() {
    try {
      // Sona eklenen "?t=..." her seferinde farklı olduğu için
      // telefon eski (önbellekteki) cevabı kullanmaz.
      const yanit = await fetch(JSON_ADRESI + '?t=' + Date.now());
      if (!yanit.ok) throw new Error('HTTP ' + yanit.status);
      const veri = await yanit.json();
      if (!Array.isArray(veri.kesintiler)) throw new Error('Beklenmeyen veri');
      setKesintiler(veri.kesintiler);
      // Eski biçimdeki dosyada geçmiş olmayabilir; o zaman boş liste
      setGecmis(Array.isArray(veri.gecmis) ? veri.gecmis : []);
      setGuncelleme(veri.guncelleme);
      setHata(false);
      await yenileriIsaretle(veri.kesintiler);
    } catch (e) {
      setHata(true);
    }
  }

  // Son açılıştan beri çıkan kesintileri bulur ve "YENİ" diye işaretler.
  // Telefonda, en son görülen kesintilerin id listesini saklıyoruz; bu listede
  // olmayan her kesinti yenidir. Etiket uygulama kapanana kadar kalır.
  async function yenileriIsaretle(liste) {
    const idler = liste.map((kesinti) => kesinti.id);
    try {
      const kayitli = await AsyncStorage.getItem(GORULEN_ANAHTARI);
      // Uygulama ilk kez açılıyorsa kayıt yoktur; o zaman her şey "yeni" görünmesin
      if (kayitli !== null) {
        const gorulenler = JSON.parse(kayitli);
        const yeniler = idler.filter((id) => !gorulenler.includes(id));
        setYeniIdler((onceki) => [...onceki, ...yeniler]);
      }
      await AsyncStorage.setItem(GORULEN_ANAHTARI, JSON.stringify(idler));
    } catch (e) {
      // Telefon hafızası okunamazsa sadece etiket çıkmaz, uygulama çalışmaya devam eder
    }
  }

  // Uygulama açılınca bir kez çalışır: kayıtlı ilçeyi oku, veriyi indir
  useEffect(() => {
    async function baslat() {
      const kayitli = await AsyncStorage.getItem(ILCE_ANAHTARI).catch(() => null);
      if (kayitli) setSecilenIlce(kayitli);
      await veriyiGetir();
      setYukleniyor(false);
    }
    baslat();
  }, []);

  // Listeyi aşağı çekince
  async function yenile() {
    setYenileniyor(true);
    await veriyiGetir();
    setYenileniyor(false);
  }

  // Hata ekranındaki "Tekrar dene" butonu
  async function tekrarDene() {
    setYukleniyor(true);
    await veriyiGetir();
    setYukleniyor(false);
  }

  // Listeden bir ilçe seçilince: ekranda göster, telefona kaydet, listeyi kapat
  function ilceSec(ilce) {
    setSecilenIlce(ilce);
    setModalAcik(false);
    AsyncStorage.setItem(ILCE_ANAHTARI, ilce).catch(() => {});
  }

  // Seçili ilçeye göre süzülmüş listeler
  function ilceyeGore(liste) {
    return secilenIlce === 'Tümü'
      ? liste
      : liste.filter((kesinti) => kesinti.ilce === secilenIlce);
  }
  const suAnkiler = ilceyeGore(kesintiler);
  const bitenler = ilceyeGore(gecmis);
  const gosterilenler = sekme === 'simdi' ? suAnkiler : bitenler;

  // Boş listede gösterilecek mesaj
  let bosMesaj;
  if (sekme === 'simdi') {
    bosMesaj = secilenIlce === 'Tümü' ? 'Şu an kesinti yok' : 'Bu ilçede kesinti yok';
  } else {
    bosMesaj =
      secilenIlce === 'Tümü'
        ? 'Son 30 günde biten kesinti yok'
        : 'Bu ilçede son 30 günde biten kesinti yok';
  }

  // Ekranın alt kısmı duruma göre değişir: yükleniyor / hata / liste
  let icerik;
  if (yukleniyor) {
    icerik = (
      <View style={styles.orta}>
        <ActivityIndicator size="large" color="#0b5cab" />
        <Text style={styles.ortaMetin}>Yükleniyor...</Text>
      </View>
    );
  } else if (hata) {
    icerik = (
      <View style={styles.orta}>
        <Text style={styles.ortaBaslik}>Veriler alınamadı</Text>
        <Text style={styles.ortaMetin}>İnternet bağlantını kontrol edip tekrar dene.</Text>
        <Pressable style={styles.buton} onPress={tekrarDene}>
          <Text style={styles.butonYazi}>Tekrar dene</Text>
        </Pressable>
      </View>
    );
  } else {
    icerik = (
      <FlatList
        data={gosterilenler}
        keyExtractor={(kesinti) => kesinti.id}
        renderItem={({ item }) => (
          <KesintiKarti
            kesinti={item}
            yeni={sekme === 'simdi' && yeniIdler.includes(item.id)}
          />
        )}
        contentContainerStyle={styles.liste}
        refreshing={yenileniyor}
        onRefresh={yenile}
        ListEmptyComponent={
          <View style={styles.orta}>
            <Text style={styles.ortaBaslik}>{bosMesaj}</Text>
            <Text style={styles.ortaMetin}>Yenilemek için aşağı çek.</Text>
          </View>
        }
      />
    );
  }

  return (
    <View style={styles.ekran}>
      <StatusBar barStyle="light-content" />

      {/* Üst kısım: başlık, ilçe seçimi, son güncelleme */}
      <View style={styles.ust}>
        <Text style={styles.baslik}>ASKİ Su Kesintileri</Text>
        <Pressable style={styles.ilceButonu} onPress={() => setModalAcik(true)}>
          <Text style={styles.ilceButonuYazi}>İlçe: {secilenIlce}</Text>
          <Text style={styles.ilceButonuYazi}>▼</Text>
        </Pressable>
        <Text style={styles.guncelleme}>
          Liste son değişti: {guncelleme ? tarihYaz(guncelleme) : '-'}
        </Text>

        {/* Şu an / Geçmiş seçimi; parantez içinde seçili ilçedeki sayı */}
        <View style={styles.sekmeler}>
          <Pressable
            style={[styles.sekme, sekme === 'simdi' && styles.sekmeSecili]}
            onPress={() => setSekme('simdi')}
          >
            <Text style={sekme === 'simdi' ? styles.sekmeYaziSecili : styles.sekmeYazi}>
              Şu an ({suAnkiler.length})
            </Text>
          </Pressable>
          <Pressable
            style={[styles.sekme, sekme === 'gecmis' && styles.sekmeSecili]}
            onPress={() => setSekme('gecmis')}
          >
            <Text style={sekme === 'gecmis' ? styles.sekmeYaziSecili : styles.sekmeYazi}>
              Geçmiş ({bitenler.length})
            </Text>
          </Pressable>
        </View>
      </View>

      {icerik}

      {/* İlçe seçme penceresi */}
      <Modal visible={modalAcik} transparent onRequestClose={() => setModalAcik(false)}>
        {/* Karartılmış arka plan; boş yere dokununca pencere kapanır */}
        <Pressable style={styles.modalArka} onPress={() => setModalAcik(false)}>
          <View style={styles.modalKutu}>
            <Text style={styles.modalBaslik}>İlçe seç</Text>
            <FlatList
              data={ILCELER}
              keyExtractor={(ilce) => ilce}
              renderItem={({ item }) => (
                <Pressable style={styles.ilceSatiri} onPress={() => ilceSec(item)}>
                  <Text style={item === secilenIlce ? styles.ilceSecili : styles.ilceYazi}>
                    {item}
                  </Text>
                  {item === secilenIlce && <Text style={styles.ilceSecili}>✓</Text>}
                </Pressable>
              )}
            />
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  ekran: { flex: 1, backgroundColor: '#f2f4f7' },

  // Üst kısım
  ust: {
    backgroundColor: '#0b5cab',
    paddingTop: UST_BOSLUK + 8,
    paddingHorizontal: 16,
    paddingBottom: 12,
  },
  baslik: { color: '#fff', fontSize: 22, fontWeight: 'bold', marginBottom: 12 },
  ilceButonu: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#fff',
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  ilceButonuYazi: { fontSize: 16, color: '#1a1a1a' },
  guncelleme: { color: '#dbe8f6', fontSize: 13, marginTop: 10 },
  sekmeler: {
    flexDirection: 'row',
    marginTop: 12,
    backgroundColor: '#094c8f',
    borderRadius: 8,
    padding: 3,
  },
  sekme: { flex: 1, paddingVertical: 8, borderRadius: 6, alignItems: 'center' },
  sekmeSecili: { backgroundColor: '#fff' },
  sekmeYazi: { color: '#dbe8f6', fontSize: 15 },
  sekmeYaziSecili: { color: '#0b5cab', fontSize: 15, fontWeight: 'bold' },

  // Liste ve kartlar
  liste: { padding: 16, paddingBottom: 40, flexGrow: 1 },
  kart: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#e1e5ea',
  },
  kartUst: { flexDirection: 'row', alignItems: 'center' },
  kartIlce: { fontSize: 20, fontWeight: 'bold', color: '#0b5cab' },
  yeniEtiketi: {
    marginLeft: 8,
    backgroundColor: '#d92d20',
    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden', // iOS'ta köşe yuvarlaması yazıda da görünsün diye
  },
  kartKaynak: { fontSize: 14, color: '#5b6470', marginTop: 2 },
  saatSatiri: { flexDirection: 'row', marginTop: 4 },
  saatKutusu: { flex: 1 },
  etiket: { fontSize: 12, color: '#5b6470', marginTop: 12, marginBottom: 2 },
  saat: { fontSize: 16, fontWeight: '600', color: '#1a1a1a' },
  metin: { fontSize: 15, lineHeight: 21, color: '#1a1a1a' },

  // Ortalanmış durum mesajları (yükleniyor, hata, boş liste)
  orta: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  ortaBaslik: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a', marginBottom: 6 },
  ortaMetin: { fontSize: 15, color: '#5b6470', textAlign: 'center', marginTop: 6 },
  buton: {
    backgroundColor: '#0b5cab',
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 28,
    marginTop: 18,
  },
  butonYazi: { color: '#fff', fontSize: 16, fontWeight: '600' },

  // İlçe seçme penceresi
  modalArka: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    padding: 24,
  },
  modalKutu: { backgroundColor: '#fff', borderRadius: 12, maxHeight: '75%', paddingVertical: 8 },
  modalBaslik: { fontSize: 18, fontWeight: 'bold', paddingHorizontal: 16, paddingVertical: 10 },
  ilceSatiri: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 13,
    paddingHorizontal: 16,
    borderTopWidth: 1,
    borderTopColor: '#eef0f3',
  },
  ilceYazi: { fontSize: 16, color: '#1a1a1a' },
  ilceSecili: { fontSize: 16, color: '#0b5cab', fontWeight: 'bold' },
});
