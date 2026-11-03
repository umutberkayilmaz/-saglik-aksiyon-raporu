# -*- coding: utf-8 -*-
"""
YORUM TEMALARI (anahtar kelime kurallari)

Her yorum Turkce karakterler sadelestirilerek (ç->c, ğ->g, ı->i, ö->o, ş->s, ü->u) kucuk harfe cevrilir;
boylece "çalışmıyor" ile "calismiyor" ayni sekilde yakalanir. Kurallar da bu sade yaziyla yazilir.

Her temanin uc kural listesi var:
  olumsuz : bu ifadelerden biri geciyorsa o tema SIKAYET sayilir
  olumlu  : (olumsuz yoksa) bu ifadelerden biri geciyorsa o tema MEMNUNIYET sayilir
            ("kaliteli degil", "hizli degil" gibi arkasindan 'degil / yok' gelenler sikayete doner)
  notr    : sadece konu gecen ifadeler ("kargo", "paket"...). Olumlu/olumsuz ifade yoksa yorumun yildizina bakilir:
            4-5 yildiz memnuniyet, 1-3 yildiz sikayet.

Yeni kelime eklemek icin ilgili listeye bir satir eklemek yeterli (regex; \\b kelime siniri demektir).
"""
import re

URUN, SATICI = "Ürün", "Satıcı & Kargo"

TEMALAR = [
    {"ad": "Ölçüm doğruluğu", "grup": URUN,
     "olumsuz": [r"yanlis olc", r"hatali olc", r"tutarsiz", r"farkli (deger|sonuc|olc|rakam|derece)",
                 r"her (seferinde|olcumde|olcusunde) (farkli|baska)", r"dogru (olcmu|olcmedi|gostermi|sonuc vermi)",
                 r"guvenilmez", r"guvenemiyorum", r"\bsapma", r"derece (fark|yuksek|dusuk|sapma)",
                 r"(yuksek|dusuk|alakasiz|sacma|abuk) (gosteri|olcu|deger|sonuc|cikiyor)",
                 r"olcumler(i)? (tutmu|uyusmu|alakasiz|tutarsiz)", r"emin olamiyorum", r"\bsasiriyor",
                 r"birbirini tutmu"],
     "olumlu": [r"dogru olc", r"dogru sonuc", r"dogru gosteri", r"\bhassas", r"\btutarli", r"\bguvenilir",
                r"net (olcum|sonuc|olcuyor)", r"olcumler(i)? (cok )?(dogru|tutarli|basarili|net|guvenilir)",
                r"(hastane|doktor|eczane)(deki|daki|nin|in)? (cihaz|olcum|deger)\w* (ile|la|le)? ?ayni",
                r"ayni (degeri|sonucu) (veriyor|gosteriyor)", r"\bisabetli"],
     "notr": [r"\bolcum(ler|u|leri|de|da)?\b"]},

    {"ad": "Ölçüm hızı", "grup": URUN,
     "olumsuz": [r"(yavas|gec|uzun surede) olc", r"olcum(u)? (cok )?(uzun suruyor|yavas)", r"cok bekletiyor"],
     "olumlu": [r"hizli olc", r"\bsaniye", r"aninda (olc|sonuc|gosteri)", r"cabuk olc", r"hemen (olc|sonuc|gosteri)",
                r"olcum(u)? (cok )?(hizli|cabuk)"],
     "notr": []},

    {"ad": "Kullanım kolaylığı", "grup": URUN,
     "olumsuz": [r"kullanimi (cok )?(zor|karisik|zahmetli|sikinti)", r"\bkarmasik", r"anlasilmi(yor|or)",
                 r"\bkullanissiz", r"zor kullan", r"ekran(i)? (cok )?(kucuk|okunmu|gorunmu|karanlik|silik|isiksiz)",
                 r"(kilavuz|talimat)(u|i)? (yok|yetersiz|ingilizce)", r"turkce (yok|degil|kilavuz yok)",
                 r"sesi? (cok )?(yuksek|rahatsiz)", r"ayarlamasi zor"],
     "olumlu": [r"\bkullanisli", r"kullanimi (cok |gayet |son derece )?(kolay|rahat|basit|pratik|zahmetsiz)",
                r"kolay kullan", r"\bpratik", r"rahat kullan", r"\bergonomik", r"\bokunakli",
                r"ekran(i)? (cok )?(net|buyuk|genis|aydinlik|isikli|anlasilir)", r"\bhafif",
                r"tek tus", r"kolayca"],
     "notr": [r"\bekran", r"\bkullanim"]},

    {"ad": "Arıza / çalışmama", "grup": URUN,
     "olumsuz": [r"calismi(yor|di|yo)", r"\bcalismaz", r"\bbozuk", r"\bbozul", r"\bariza", r"acilmi(yor|di)",
                 r"hata (veri|kodu|mesaji)", r"\berr\b", r"\berror", r"\bdefolu", r"kendi kendine (kapan|acil)",
                 r"tepki vermi", r"\bsondu", r"bir (kac|iki) (kullanim|gun|hafta)(da|ta)? (bozul|gitti)",
                 r"islevini yitir", r"calismaz hale"],
     "olumlu": [r"sorunsuz (calis|kullan)", r"hic (bir )?sorun (yasamadim|cikmadi|yok)", r"yillardir kullan",
                r"\bsorunsuz"],
     "notr": []},

    {"ad": "Pil / batarya", "grup": URUN,
     "olumsuz": [r"pil(i|ler|leri)? (cok )?(cabuk|hemen|erken) (bit|bitiyor|bitti|tukeni)",
                 r"pil(i|leri)? (yok|gelmedi|cikmadi|bitik|bitmis|dahil degil)", r"pil haric",
                 r"sarj(i)? (cok )?(cabuk|hemen) (bit|gidiyor)", r"pil yemek"],
     "olumlu": [r"pil(i|leri)? (de )?(dahil|hediye|uzun omurlu|uzun gidiyor|ile birlikte|ile geldi|gonderil|verilmis|vardi|mevcut)",
                r"pil(ler)?le birlikte", r"sarji (cok )?uzun"],
     "notr": [r"\bpil\b", r"\bpili\b", r"\bpiller", r"\bbatarya", r"\bsarj"]},

    {"ad": "Malzeme / kalite", "grup": URUN,
     "olumsuz": [r"\bkalitesiz", r"\bdayaniksiz", r"(ucuz|basit|kalitesiz|cürük|curuk) (plastik|malzeme|duruyor)",
                 r"cabuk (bozul|kiril|yipran)", r"\bkirildi", r"\bkirik", r"\bcatlak", r"\bcizik",
                 r"malzeme(si)? (kotu|kalitesiz|basit|ucuz)", r"oyuncak gibi"],
     "olumlu": [r"\bkaliteli", r"\bsaglam", r"kalite(si)? (cok )?(iyi|guzel|harika|super|yuksek|ust duzey)",
                r"\bsik\b", r"tasarim(i)? (cok )?(guzel|sik|harika|hos)", r"\bpremium", r"birinci sinif",
                r"\bguzel urun", r"\bdayanikli"],
     "notr": [r"\bmalzeme", r"\bkalite"]},

    {"ad": "Aksesuar / içerik", "grup": URUN,
     "olumsuz": [r"manset(i)? (cok )?(kucuk|dar|buyuk|bol|sikiyor|rahatsiz|kotu|kisa)",
                 r"(kapak|kapsul|filtre|aparat|baslik|adaptor|kablo|canta|kilif)(lar|ler)?(i|u|si)? (yok|eksik|gelmedi|cikmadi|ayri satiliyor)",
                 r"aksesuar(lar)? (yok|eksik)", r"adaptor(u)? yok"],
     "olumlu": [r"manset(i)? (cok )?(rahat|kaliteli|iyi|genis|guzel)",
                r"(canta|kilif|saklama kab|saklama kutu)\w* (ile|de|da|hediye|var|mevcut|guzel)",
                r"(kapak|kapsul|filtre|yedek)\w* (hediye|ile birlikte|de geldi|da geldi|gonderil)",
                r"iki (tane )?manset"],
     "notr": [r"\bmanset", r"\baksesuar", r"\bkapsul", r"\bfiltre", r"\bcanta", r"\bkilif"]},

    {"ad": "Fiyat / performans", "grup": URUN,
     "olumsuz": [r"\bpahali", r"fiyat(i)? (cok |biraz )?(yuksek|fazla|pahali)", r"fiyatina (degmez|gore kotu)",
                 r"paraya yazik", r"parasina degmez", r"\bfahis", r"\bkazik"],
     "olumlu": [r"fiyat ?(\/ ?)?performans", r"fiyatina (gore|degecek|deger)", r"uygun fiyat",
                r"fiyat(i)? (cok )?(uygun|guzel|makul|iyi|ideal)", r"\bindirim(de|li|le|den)",
                r"ucuz(a)? (aldim|geldi|aldik)", r"parasina (deger|degiyor)", r"\bkampanya(da|li)"],
     "notr": [r"\bfiyat"]},

    {"ad": "Genel memnuniyet", "grup": URUN,
     "olumsuz": [r"tavsiye (etmem|etmiyorum|edemem)", r"\bonermem", r"\bonermiyorum",
                 r"memnun (degilim|kalmadim|kalmadik|degiliz)", r"\bpisman", r"hayal kirikligi",
                 r"\bberbat", r"\brezalet", r"\bbegenmedim", r"\balmayin", r"\bvasat", r"\bfelaket"],
     "olumlu": [r"tavsiye ederim", r"tavsiye ediyorum", r"\boneririm", r"\boneriyorum",
                r"\bmemnun(um|uz|kaldim|kaldik)", r"(cok|gayet|oldukca) (begendim|memnun|guzel)",
                r"\bharika", r"\bmukemmel", r"\bbayildim", r"\bsuper\b", r"\befsane", r"10 numara",
                r"\bbegendim", r"\bkusursuz"],
     "notr": []},

    # ---------------- satici & kargo (urunden bagimsiz) ----------------
    {"ad": "Kargo hızı", "grup": SATICI,
     "olumsuz": [r"(kargo|teslimat|gonderim)(si|u)? (cok )?(gec|yavas|gecikti|gecikmeli|rezalet|berbat)",
                 r"gec (geldi|teslim|ulasti|gonder|kargola)", r"\bgecikme", r"\bgecikti",
                 r"(hafta|gun)(dir|dur)? (bekledim|bekliyorum|gelmedi)", r"(cok|uzun|gunlerce) bekle",
                 r"kargoya (gec|gec verildi)", r"hala gelmedi", r"gec kargo"],
     "olumlu": [r"hizli (kargo|teslim|geldi|gonder|ulasti|elime)", r"(kargo|teslimat|gonderim)(si|u)? (cok |gayet |super )?(hizli|cabuk|seri)",
                r"ertesi gun", r"(ayni|bir|1|iki|2) gunde (geldi|elime|teslim|ulasti)", r"cabuk (geldi|ulasti|teslim)",
                r"(erken|zamaninda|vaktinde) (geldi|teslim|ulasti)", r"\bhizlica", r"isik hizi"],
     "notr": [r"\bkargo(?!la)", r"\bteslimat"]},

    {"ad": "Paketleme / hasar", "grup": SATICI,
     "olumsuz": [r"(ezik|ezilmis|hasarli|yirtik|yirtilmis|parcalanmis|kirik|islak) (kutu|paket|ambalaj|geldi)",
                 r"(kutu|paket|ambalaj)(u|i|si)? (ezik|ezilmis|ezilerek|hasarli|yirtik|parcalanmis|kotu|berbat|dagilmis)",
                 r"(poset|zarf)(e|le|la|in)? (konul|koyul|gonder|gel|sarilmadan)", r"paketleme(si)? (cok )?(kotu|ozensiz|berbat|yok|yetersiz)",
                 r"\bozensiz", r"korumasiz", r"balonlu naylon (yok|olmadan)"],
     "olumlu": [r"(ozenli|guzel|saglam|guvenli|iyi|ozenle|duzgun|harika|super|ozel) (paket|ambalaj|kargola|kutu)",
                r"paketleme(si)? (cok |gayet )?(iyi|ozenli|guzel|saglam|harika|super|basarili)",
                r"(kutu|paket)(u|i)? (saglam|hasarsiz|sorunsuz)", r"zarar gormeden", r"\bozenli",
                r"kargolama(si)? (cok |gayet )?(iyi|guzel|ozenli|saglam|harika|super|basarili)"],
     "notr": [r"\bpaket", r"\bambalaj", r"\bkargola"]},

    {"ad": "Orijinallik / garanti", "grup": SATICI,
     "olumsuz": [r"(orijinal|orjinal)(lig)?(i|ligi)? (degil|olmadig|mi acaba|mi bilmiyorum|oldugundan emin degil|supheli|suphe)",
                 r"\bsahte", r"\bcakma", r"\bimitasyon", r"garanti(si| belgesi)? (yok|gelmedi|cikmadi|gonderilmedi|verilmedi)",
                 r"\bfaturasiz", r"fatura(si)? (gelmedi|yok|gonderilmedi|kesilmedi)", r"(yurt ?disi|ithal|gri) (urun|mali|cikti|pazar)",
                 r"(ingilizce|yabanci|almanca|arapca) (kutu|ambalaj|kilavuz)", r"turkce (kutu|ambalaj|kilavuz)(su)? (degil|yok)"],
     "olumlu": [r"\b(orijinal|orjinal)", r"\bgarantili", r"garanti belgesi (var|geldi|ile|mevcut)", r"\bfaturali",
                r"resmi (distributor|ithalatci|satici|bayi)", r"yetkili satici"],
     "notr": [r"\bgaranti", r"\bfatura"]},

    {"ad": "Kusurlu / eksik gönderim", "grup": SATICI,
     "olumsuz": [r"(kullanilmis|ikinci el|acilmis|teshir) (urun|geldi|gonder|gibi)", r"(yanlis|farkli|baska) (urun|model|renk) (geldi|gonder)",
                 r"eksik (geldi|gonder|parca|urun)", r"(kutu|ambalaj)(su|si|u)? acilmis", r"jelatin(i)? (yok|acik|acilmis|yirtik)",
                 r"bandi (acik|acilmis|kesilmis)", r"\bkutusuz", r"(urun|cihaz) (eksik|kirik) (geldi|cikti)"],
     "olumlu": [r"jelatin(i|li)? (ile|uzerinde|acilmamis|kapali|saglam)", r"(sifir|yepyeni|kapali kutu|acilmamis) (geldi|urun|kutu)"],
     "notr": []},

    {"ad": "Satıcı / iade ilgisi", "grup": SATICI,
     "olumsuz": [r"satici(ya|nin|da)? (cok )?(ilgisiz|cevap vermi|donus yapmi|ulasilami|ilgilenmi|yardimci olmadi)",
                 r"\bilgisiz", r"iade(yi|mi)? (kabul etmi|kabul etmedi|alinmadi|edemedim|etmediler|yapilmadi|reddedil|almadi)",
                 r"(cevap|donus) (vermiyor|vermedi|yapmadi|yapilmadi|yok)", r"\bmagdur", r"musteri hizmetleri (kotu|ilgisiz|ulasilami)"],
     "olumlu": [r"satici(ya|nin)? (cok )?(ilgili|guvenilir|harika|super|kibar|anlayisli|yardimci)", r"ilgili (satici|firma)",
                r"satici(nin)? (ilgisi|ozeni|tesekkur)", r"(iade|degisim)(i)? (sorunsuz|hizli|kolay)",
                r"(satici|saticiya|firmaya|magazaya) tesekkur", r"tesekkurler (satici|braun)"],
     "notr": [r"\bsatici", r"\biade", r"\bdegisim"]},
]

_HARF = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})
_DERLENMIS = [{**t, **{k: [re.compile(p) for p in t.get(k, [])] for k in ("olumsuz", "olumlu", "notr")}}
              for t in TEMALAR]
_OLUMSUZLUK = re.compile(r"^\W{0,3}(\w+ ){0,1}(degil|yok|olmadi|olmamis|degildi)\b")


def sadele(metin):
    t = str(metin or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    t = t.translate(_HARF)
    t = re.sub(r"(.)\1{2,}", r"\1", t)                # "cokkkk" -> "cok"
    t = re.sub(r"[^a-z0-9/ ]+", " ", t)
    return " " + " ".join(t.split()) + " "


def _olumlu_mu(desen, metin):
    """Olumlu ifade geciyor mu? Arkasindan 'degil / yok' geliyorsa olumsuz sayilir. (eslesti, tersine_dondu)"""
    tersine = False
    for m in desen.finditer(metin):
        if _OLUMSUZLUK.search(metin[m.end():m.end() + 20]):
            tersine = True
            continue
        return True, tersine
    return False, tersine


def temalari_bul(metin, yildiz=None):
    """(olumlu_temalar, olumsuz_temalar) listeleri doner."""
    t = sadele(metin)
    olumlu, olumsuz = [], []
    if len(t.strip()) < 2:
        return olumlu, olumsuz
    for tema in _DERLENMIS:
        if any(d.search(t) for d in tema["olumsuz"]):
            olumsuz.append(tema["ad"])
            continue
        bulundu, tersine = False, False
        for d in tema["olumlu"]:
            b, tr = _olumlu_mu(d, t)
            tersine = tersine or tr
            if b:
                bulundu = True
                break
        if bulundu:
            olumlu.append(tema["ad"])
        elif tersine:
            olumsuz.append(tema["ad"])
        elif yildiz and any(d.search(t) for d in tema["notr"]):
            (olumlu if yildiz >= 4 else olumsuz).append(tema["ad"])
    return olumlu, olumsuz


def tema_gruplari():
    return {t["ad"]: t["grup"] for t in TEMALAR}
