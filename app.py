import streamlit as st
import pandas as pd
import re
import io
import json
import os
import base64
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
import tasarim

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık · Fiyat & Buybox", page_icon=tasarim.favicon(), layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
# Sheet'in kimliği (adres çubuğunda /d/ ile /edit arasındaki uzun kod). Doluysa dosya adla aranmaz,
# doğrudan bu kodla açılır; ad değişse bile bağlantı kopmaz. Streamlit secrets'a gsheet_id olarak da yazılabilir.
GSHEET_ID = ""
GSHEET_WORKSHEET = "Guncel"
BUYBOX_WORKSHEET = "BuyBox"
YORUM_OZET_WORKSHEET = "Yorum_Ozet"     # yorum_script.py'nin yazdigi sayfalar
YORUM_WORKSHEET = "Yorumlar"
YORUM_GECIKME_ESIGI_DK = 5 * 24 * 60     # yorum taramasi (Pazartesi + Persembe) bundan eskiyse uyari
DURUM_WORKSHEET = "Durum"             # ana script'in yazdigi platform tarama durumlari
GECIKME_ESIGI_DK = 120                # fiyat taramasi (saat basi) bundan eskiyse panel uyari gosterir
BB_GECIKME_ESIGI_DK = 26 * 60         # BuyBox taramasi (gunde 1) bundan eskiyse BuyBox sekmesi uyari gosterir
BUYUK_SAPMA_YUZDE = 15

# ================= PANEL AYARLARI (buradan düzenleyebilirsin) =================
ESIK_YUZDE = 5          # Sarı ile kırmızı arasındaki sınır: TSF'nin %5'ten fazla altındaki fiyatlar kırmızı olur
AKAKCE_GOSTER = True    # TSF sütununun altında Akakçe'deki piyasa en ucuz fiyatı yazsın mı (True / False)
KANALLAR = ["Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]

# Kanal logoları. Trendyol ve Hepsiburada: sitelerin kendi sunucularındaki güncel, şeffaf logolar.
# Adresi boş bırakılan kanalda tasarim.py'deki logo kullanılır (Braunshop: BAY, N11 ve İdefix: gönderdiğin logolar).
# Repoya PLATFORM_LOGO_DOSYALARI adlarıyla (örn. braunshop.png) dosya yüklersen o dosya hepsinin önüne geçer.
KANAL_LOGO_ADRESLERI = {
    "Braunshop": "",
    "Trendyol": "https://cdn.dsmcdn.com/sfweb-browsing/images/trendyol-logo_1761301016237.svg",
    "Hepsiburada": "https://images.hepsiburada.net/storefront/storefront/www/assets/images/hepsiburada.svg",
    "N11": "",
    "İdefix": "",
}

# Platform basliklarindaki logolar: GitHub'da repoya (ya da "logos" klasorune) bu adlarla PNG yuklersen
# o logo kullanilir; yuklemezsen sitenin kendi kucuk ikonu ve adi gosterilir.
PLATFORM_LOGO_DOSYALARI = {"Akakçe": "akakce.png", "Braunshop": "braunshop.png", "Trendyol": "trendyol.png",
                           "Hepsiburada": "hepsiburada.png", "N11": "n11.png", "İdefix": "idefix.png"}
PLATFORM_COLS = ["Akakçe", "Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]

st.markdown("""
<style>
    .pill { padding: 4px 12px; border-radius: 20px; font-weight: 600; display: inline-block; text-decoration: none !important; }
    .pill-green { background-color: rgba(0, 184, 76, 0.15); color: #00873c; }
    .pill-yellow { background-color: rgba(255, 193, 7, 0.2); color: #8a6500; }
    .pill-red { background-color: rgba(220, 53, 69, 0.15); color: #a71d2a; }
    .pill-plain { background-color: rgba(128,128,128,0.12); color: inherit; }
    .pill-lowest { box-shadow: 0 0 0 2px #00873c inset; }
    .lowest-badge { font-size: 10px; margin-left: 4px; }
    a.pill:hover { filter: brightness(0.95); cursor: pointer; }
    .update-badge { color: #888; font-size: 12px; background: rgba(128,128,128,0.1); padding: 5px 14px; border-radius: 30px; }
    table td, table th { text-align: center !important; padding: 8px 10px !important; }
    .thumb { position: relative; display: inline-block; cursor: zoom-in; }
    .thumb > img { width: 46px; height: 46px; object-fit: contain; background: #fff; border-radius: 8px;
                   border: 1px solid rgba(128,128,128,0.2); }
    .thumb-buyuk { visibility: hidden; opacity: 0; position: absolute; left: 115%; top: 50%;
                   transform: translateY(-50%); z-index: 9999; background: #fff; padding: 6px;
                   border-radius: 12px; box-shadow: 0 10px 35px rgba(0,0,0,0.3); transition: opacity 0.15s; }
    .thumb-buyuk { width: 194px; box-sizing: border-box; }
    .thumb-buyuk img { width: 180px !important; height: 180px !important; max-width: none !important;
                       object-fit: contain; display: block; }
    .thumb:hover .thumb-buyuk { visibility: visible; opacity: 1; }
    .rapor-tablo th { text-transform: uppercase; font-size: 11px !important; color: #888 !important;
                      font-weight: 600 !important; letter-spacing: 0.3px; vertical-align: middle !important; }
    .plat-baslik a { text-decoration: none !important; color: inherit !important; }
    .plat-logo { height: 24px; max-width: 110px; object-fit: contain; display: block; margin: 0 auto;
                 transition: transform 0.2s; }
    .plat-ikon { width: 18px; height: 18px; vertical-align: middle; margin-right: 6px; border-radius: 4px; }
    .plat-ad { font-size: 13px; color: inherit; text-transform: none; font-weight: 700; vertical-align: middle; }
    .plat-baslik:hover .plat-logo { transform: scale(1.08); }
    .plat-sayi { font-size: 10px; margin-top: 5px; text-transform: none; font-weight: 700; color: #888; }
    .barkod { font-variant-numeric: tabular-nums; cursor: help; }
    .sirket-baslik { display: flex; align-items: center; gap: 16px; margin: 0.4rem 0 0.8rem 0; flex-wrap: wrap; }
    .sirket-baslik img { height: 52px; width: auto; }
    .sirket-baslik span { font-size: 2.2rem; font-weight: 700; line-height: 1.2; }
</style>
""", unsafe_allow_html=True)


# Gorsellerde referrerpolicy="no-referrer" kullaniliyor; gorsel sunucusu baska siteden gelen istegi engellemesin diye.


def dosyadan_data_uri(dosya_adi):
    for yol in (os.path.join("logos", dosya_adi), dosya_adi):
        if os.path.exists(yol):
            try:
                with open(yol, "rb") as f:
                    return "data:image/png;base64," + base64.b64encode(f.read()).decode()
            except Exception:
                pass
    return None


# ================= GOOGLE SHEETS BAĞLANTISI =================
@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Google Sheets bağlantı hatası: {e}")
        return None


def _tablo_ac(client):
    """Sheet'i önce kimliğiyle (varsa), yoksa adıyla açar."""
    kimlik = GSHEET_ID
    try:
        kimlik = kimlik or str(st.secrets.get("gsheet_id", "") or "")
    except Exception:
        pass
    if kimlik.strip():
        return client.open_by_key(kimlik.strip())
    return client.open(GSHEET_NAME)


def _panel_hesabi():
    try:
        return str(st.secrets["gcp_service_account"].get("client_email", ""))
    except Exception:
        return ""


def extract_url(formula_val):
    """='=HYPERLINK(\"url\"; fiyat)' formulunden url'i cikarir."""
    if isinstance(formula_val, str) and "HYPERLINK" in formula_val.upper():
        m = re.search(r'HYPERLINK\(\s*["\']([^"\']+)["\']', formula_val, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def parse_price_from_cell(val):
    """Hem duz sayilari hem HYPERLINK formul metnini fiyata cevirir."""
    if val is None or val == "":
        return None
    s = str(val)
    if "HYPERLINK" in s.upper():
        m = re.search(r';\s*([\d.,]+)\s*\)', s)
        if m:
            s = m.group(1)
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=180)
def load_data():
    client = get_gspread_client()
    if not client:
        return None, ""

    try:
        sh = _tablo_ac(client)
        ws = sh.worksheet(GSHEET_WORKSHEET)

        values = ws.get_all_values()
        formulas = ws.get_all_values(value_render_option="FORMULA")
        if not values:
            return None, ""

        headers = [str(h).strip() for h in values[0]]
        update_text = next((h for h in headers if h.startswith("Son Güncelleme")), "")
        if not update_text:
            try:
                update_text = ws.acell("N1").value or ""
            except Exception:
                pass
        if "TSF" not in headers and "Hedef Fiyat" in headers:
            headers = ["TSF" if h == "Hedef Fiyat" else h for h in headers]
        rows = values[1:]
        formula_rows = formulas[1:]

        df = pd.DataFrame(rows, columns=headers)
        df_formula = pd.DataFrame(formula_rows, columns=headers)

        for col in ["TSF", "Kampanya Fiyatı", "En Düşük Fiyat"]:
            if col in df.columns:
                df[col] = df[col].apply(parse_price_from_cell)

        for col in PLATFORM_COLS:
            if col in df.columns:
                df[f"{col}_fiyat"] = df_formula[col].apply(parse_price_from_cell)
                df[f"{col}_link"] = df_formula[col].apply(extract_url)

        return df, update_text
    except gspread.SpreadsheetNotFound:
        st.error(f"Panel, Google Sheets'te '{GSHEET_NAME}' dosyasını göremiyor. Panelin bağlandığı hesap: "
                 f"{_panel_hesabi() or 'okunamadı'}. Dosya bu adresle Düzenleyen olarak paylaşılmış olmalı.")
        return None, ""
    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets erişim hatası ({getattr(e, 'code', '')}). Panelin bağlandığı hesap: "
                 f"{_panel_hesabi() or 'okunamadı'} — dosyanın bu adresle paylaşıldığını kontrol edin.")
        return None, ""
    except Exception as e:
        st.error(f"Veri okunurken hata: {e}")
        return None, ""


def kampanya_penceresi():
    """Kampanya listesinin geçerlilik aralığı (başlangıç, bitiş) ya da None."""
    d = load_durum().get("Kampanya listesi") or {}
    if d.get("durum") != "Tamam":
        return None
    tarihler = re.findall(r"\d{2}\.\d{2}\.\d{4}", d.get("son_basarili", ""))
    if len(tarihler) != 2:
        return None
    try:
        return tuple(datetime.strptime(t, "%d.%m.%Y").date() for t in tarihler)
    except ValueError:
        return None


AY_ADLARI = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def kampanya_etiketi():
    """Kampanya Fiyatı başlığının alt yazısı: '2-3-4 Ekim', '30-31 Ekim, 1 Kasım', '5-11 Ekim'."""
    d = load_durum().get("Kampanya listesi") or {}
    if d.get("durum") == "Süresi doldu":
        return "Aktif kampanya yok"
    pencere = kampanya_penceresi()
    if not pencere:
        return "Hafta sonu"
    bas, bit = pencere
    gunler = [bas + timedelta(days=i) for i in range((bit - bas).days + 1)]
    if len(gunler) > 4:
        if bas.month == bit.month:
            return f"{bas.day}-{bit.day} {AY_ADLARI[bit.month - 1]}"
        return f"{bas.day} {AY_ADLARI[bas.month - 1]} - {bit.day} {AY_ADLARI[bit.month - 1]}"
    aylar = []
    for g in gunler:
        if not aylar or aylar[-1][0] != g.month:
            aylar.append((g.month, []))
        aylar[-1][1].append(str(g.day))
    return ", ".join(f"{'-'.join(gs)} {AY_ADLARI[ay - 1]}" for ay, gs in aylar)


def hafta_sonu_mu():
    """Kampanya dönemi mi? Kampanya listesi varsa onun tarihleri, yoksa cuma-pazar."""
    bugun = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    pencere = kampanya_penceresi()
    if pencere:
        return pencere[0] <= bugun <= pencere[1]
    return bugun.weekday() in (4, 5, 6)


def _dolu(v):
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def aktif_referans(tsf, kampanya, braunshop):
    """Cuma-Pazar kampanya fiyati (doluysa), diger gunler TSF; ikisi de yoksa Braunshop fiyati."""
    if hafta_sonu_mu() and _dolu(kampanya):
        return kampanya, "kampanya"
    if _dolu(tsf):
        return tsf, "tsf"
    return (braunshop, "braunshop") if _dolu(braunshop) else (None, "")


@st.cache_data(ttl=180)
def load_durum():
    """Platform -> {durum, son_basarili, aciklama, ...}. Sayfa yoksa bos (tum kanallar 'Tamam' sayilir)."""
    client = get_gspread_client()
    if not client:
        return {}
    try:
        ws = _tablo_ac(client).worksheet(DURUM_WORKSHEET)
        values = ws.get_all_values()
    except Exception:
        return {}
    if not values or len(values) < 2:
        return {}
    h = [str(x).strip() for x in values[0]]
    sonuc = {}
    for satir in values[1:]:
        d = dict(zip(h, satir))
        ad = str(d.get("Platform", "")).strip()
        if ad:
            sonuc[ad] = {"durum": str(d.get("Durum", "Tamam")).strip() or "Tamam",
                         "son_basarili": str(d.get("Son Başarılı Tarama", "")).strip(),
                         "aciklama": str(d.get("Açıklama", "")).strip()}
    return sonuc


def tarama_yasi_dk(guncelleme_metni):
    """'Son Güncelleme: 24.09.2026 12:05' -> kac dakika once (Turkiye saati). Okunamazsa None."""
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", str(guncelleme_metni or ""))
    if not m:
        return None
    try:
        t = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d.%m.%Y %H:%M")
    except ValueError:
        return None
    simdi = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(tzinfo=None)
    return max(0, (simdi - t).total_seconds() / 60)


# ================= FİYAT & BUYBOX SEKMESİ (Design tasarımı) =================
def _sayi(v):
    if v is None or v == "" or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bb_durumu(sahip):
    """Buybox sahibi Braun Shop ise True, başka satıcıysa False, bilgi yoksa None."""
    s = " ".join(str(sahip or "").split()).casefold()
    if not s or s in ("nan", "none", "-"):
        return None
    return s == "braun shop"


def _bb_haritasi(bb_df):
    harita = {}
    if bb_df is None or bb_df.empty:
        return harita
    for _, b in bb_df.iterrows():
        kod = str(b.get("Ürün Kodu", "") or "").strip()
        if kod:
            harita[kod] = {"Trendyol": _bb_durumu(b.get("TY BuyBox Sahibi")),
                           "Hepsiburada": _bb_durumu(b.get("HB BuyBox Sahibi"))}
    return harita


def veriyi_donustur(df, bb_df):
    """Google Sheet verisini tasarim.py'nin beklediği satır listesine çevirir."""
    bb = _bb_haritasi(bb_df)
    satirlar = []
    for _, r in df.iterrows():
        kod = str(r.get("Ürün Kodu", "") or "").strip()
        ad = " ".join(str(r.get("Ürün Adı", "") or "").split())
        barkod = str(r.get("Barkod", "") or "").strip()
        if barkod.endswith(".0"):
            barkod = barkod[:-2]
        grup = str(r.get("Alt Grup", "") or "").strip()
        tsf, kampanya = _sayi(r.get("TSF")), _sayi(r.get("Kampanya Fiyatı"))
        ref, tur = aktif_referans(tsf, kampanya, _sayi(r.get("Braunshop_fiyat")))

        notlar = []
        if tur == "kampanya":
            notlar.append("Hafta sonu kampanya fiyatı")
            if tsf:
                notlar.append(f"TSF {tasarim._fmt(tsf)}")
        elif tur == "braunshop":
            notlar.append("TSF girilmemiş, Braunshop fiyatı baz alındı")
        elif kampanya:
            notlar.append(f"H.sonu kampanya {tasarim._fmt(kampanya)}")
        akakce = _sayi(r.get("Akakçe_fiyat"))
        if AKAKCE_GOSTER and akakce:
            notlar.append(f"Akakçe en ucuz {tasarim._fmt(akakce)}")

        satirlar.append({
            "urun": kod or ad or "-",
            "marka": "",
            "kategori": " · ".join(x for x in (barkod, grup) if x),
            "tsf": ref,
            "tsf_notlari": notlar,
            "fiyatlar": {k: _sayi(r.get(f"{k}_fiyat")) for k in KANALLAR},
            "linkler": {k: (str(r.get(f"{k}_link", "") or "").strip() or None) for k in KANALLAR},
            "buybox": bb.get(kod, {}),
            "gorsel": str(r.get("Görsel", "") or ""),
            "tam_ad": ad,
            # eski düzen tablo sütunları
            "barkod": barkod, "kod": kod, "grup": grup, "tsf_gercek": tsf, "kampanya": kampanya,
            "ref_turu": tur, "akakce": akakce,
            "akakce_link": (str(r.get("Akakçe_link", "") or "").strip() or None),
            # panelin kendi kullanımı (arama, filtre, Excel)
            "_ad": ad, "_barkod": barkod, "_grup": grup, "_tsf": tsf, "_kampanya": kampanya, "_akakce": akakce,
            "_arama": " ".join((ad, kod, barkod, grup)).casefold(),
        })
    return satirlar


def _excel_verisi(satirlar):
    etiket = {"ok": "Uygun", "warn": "Sarı", "bad": "Kırmızı", "nt": "TSF yok", "none": "Satışta yok"}
    kayit = []
    for s in satirlar:
        satir = {"Barkod": s["_barkod"], "Ürün Kodu": s["urun"], "Ürün Adı": s["_ad"], "Alt Grup": s["_grup"],
                 "TSF": s["_tsf"], "Hafta Sonu Kampanya": s["_kampanya"], "Karşılaştırma Fiyatı": s["tsf"],
                 "Akakçe En Ucuz": s["_akakce"]}
        for k in KANALLAR:
            fiyat = s["fiyatlar"].get(k)
            durum_, _ = tasarim.durum(fiyat, s["tsf"], ESIK_YUZDE)
            satir[k] = fiyat
            satir[f"{k} Durum"] = etiket[durum_]
        for k in ("Trendyol", "Hepsiburada"):
            b = s["buybox"].get(k)
            satir[f"{k} Buybox"] = "Bizde" if b is True else ("Başka satıcıda" if b is False else "")
        kayit.append(satir)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame(kayit).to_excel(w, index=False, sheet_name="Fiyat_Buybox")
    return out.getvalue()


def fiyat_buybox_sayfasi(df, yas_dk=None):
    tasarim.baslik(ESIK_YUZDE)
    kanal_durumu = load_durum()
    tasarim.veri_uyarilari(kanal_durumu, yas_dk, GECIKME_ESIGI_DK)
    if df is None or df.empty:
        st.warning("Veri bulunamadı. Google Sheets bağlantısını ve sayfa adını kontrol edin.")
        return
    bb_df, bb_zaman = load_buybox()
    satirlar = veriyi_donustur(df, bb_df)

    c1, c2, c_yenile, c3 = st.columns([2.2, 2.2, 0.9, 1])
    with c1:
        ara = st.text_input("Ürün ara", placeholder="Ürün adı, kodu ya da barkod", key="fb_ara")
    with c2:
        gruplar = sorted({s["_grup"] for s in satirlar if s["_grup"]})
        secilen = st.multiselect("Alt Grup", gruplar, placeholder="Tümü", key="fb_grup")
    if ara and ara.strip():
        aranan = ara.strip().casefold()
        satirlar = [s for s in satirlar if aranan in s["_arama"]]
    if secilen:
        satirlar = [s for s in satirlar if s["_grup"] in secilen]
    with c_yenile:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Verileri yenile", key="fb_yenile", help="Elle tarama yaptıysan 3 dakikalık önbelleği beklemeden güncel veriyi getirir"):
            st.cache_data.clear()
            st.rerun()
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        zaman = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d-%m-%Y_%H-%M")
        st.download_button("📥 Excel'e Aktar", _excel_verisi(satirlar), f"Fiyat_Buybox_{zaman}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="fb_excel")

    notu = (f"BB bilgisi: {bb_zaman.replace('Son Güncelleme: ', '')} BuyBox taraması (Trendyol, Hepsiburada)."
            if bb_zaman else "BB bilgisi perşembe BuyBox taramasından sonra görünür.")
    kampanya = load_durum().get("Kampanya listesi") or {}
    pencere = kampanya_penceresi()
    if pencere:
        aralik = f"{pencere[0]:%d.%m}–{pencere[1]:%d.%m.%Y}"
        parcalar = kampanya.get("aciklama", "").split(" · ")
        ozet = parcalar[1] if len(parcalar) > 1 else ""
        notu += (f" Kampanya listesi {aralik}" + (f" ({ozet})" if ozet else "")
                 + (": bugün kampanya fiyatına göre karşılaştırılıyor." if hafta_sonu_mu()
                    else ": kampanya günlerinde kampanya fiyatına göre karşılaştırılacak."))
        if "kontrol et" in kampanya.get("aciklama", "") or "birden fazla" in kampanya.get("aciklama", ""):
            notu += " Eşleştirme uyarısı var: ayrıntılar için Sheet'teki Durum sayfasına bakın."
    elif kampanya.get("durum") == "Süresi doldu":
        notu += " Son kampanya listesinin süresi doldu; karşılaştırma TSF'ye göre."
    elif kampanya.get("durum") == "Okunamadı":
        notu += f" Kampanya listesi okunamadı ({kampanya.get('aciklama', '')[:80]})."
    elif hafta_sonu_mu():
        notu += " Hafta sonu: kampanya fiyatı girilmiş ürünler kampanya fiyatına göre karşılaştırılır."
    tasarim.govde(satirlar, ESIK_YUZDE, tablo_notu=notu, klasik=True, akakce_goster=AKAKCE_GOSTER,
                  kanal_durumu=kanal_durumu, kampanya_etiketi=kampanya_etiketi())


# ================= BUYBOX SEKMESİ =================
@st.cache_data(ttl=180)
def load_buybox():
    client = get_gspread_client()
    if not client:
        return None, ""
    try:
        ws = _tablo_ac(client).worksheet(BUYBOX_WORKSHEET)
    except gspread.WorksheetNotFound:
        return None, ""
    except Exception as e:
        st.error(f"BuyBox verisi okunurken hata: {e}")
        return None, ""

    values = ws.get_all_values()
    if not values or len(values) < 2:
        return None, ""
    formulas = ws.get_all_values(value_render_option="FORMULA")
    header = [str(h).strip() for h in values[0]]
    zaman = next((h for h in header if h.startswith("Son Güncelleme")), "")

    df = pd.DataFrame(values[1:], columns=header)
    df_f = pd.DataFrame(formulas[1:], columns=header)
    for col in ["Tavsiye Fiyat", "En Ucuz Rakip Fiyat", "Önerilen BuyBox Fiyatı", "Fark (TL)", "Fark (%)",
                "Braun Shop TY", "Braun Shop HB"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_price_from_cell)
    for col in ["TY Rakip Fiyat", "HB Rakip Fiyat"]:
        if col in df.columns:
            df[f"{col}_fiyat"] = df_f[col].apply(parse_price_from_cell)
            df[f"{col}_link"] = df_f[col].apply(extract_url)
    return df, zaman


def gun_bandi_goster():
    gun = (datetime.now(timezone.utc) + timedelta(hours=3)).weekday()
    if gun == 3:
        tasarim.bant("bilgi", "Perşembe: BuyBox hazırlık günü.",
                     "Aşağıdaki önerilen fiyatları Trendyol ve Hepsiburada'da uygula; fiyatlar Cuma, Cumartesi ve "
                     "Pazar boyunca geçerli olacak.", "📅")
    elif gun in (4, 5, 6):
        tasarim.bant("basari", "BuyBox dönemi (Cuma-Pazar).", "Perşembe belirlenen fiyatlar aktif olmalı.", "🛒")
    elif gun == 0:
        tasarim.bant("uyari", "Pazartesi: TSF'ye dönüş günü.",
                     "BuyBox için indirdiğin fiyatları tavsiye satış fiyatına geri çek.", "↩️")
    else:
        tasarim.bant("normal", "Normal dönem.",
                     "Tavsiye satış fiyatları geçerli; bir sonraki BuyBox önerisi Perşembe hazırlanacak.", "ℹ️")


def _siralama_oku(deger):
    """BuyBox script'inin yazdığı sıralama JSON'unu okur; yoksa ya da bozuksa None."""
    try:
        d = json.loads(str(deger)) if deger else None
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) and d.get("ilk") else None


def _siralama_metni(d):
    if not d:
        return ""
    metin = " · ".join(f"{i}) {x.get('ad', '')} {x.get('fiyat', 0):g}" for i, x in enumerate(d["ilk"], 1))
    if d.get("braun_sira") and d["braun_sira"] > len(d["ilk"]):
        metin += f" · Braun Shop: {d['braun_sira']}. sıra"
    for x in d.get("diger") or []:
        metin += f" · Diğer ilan: {x.get('ad', '')} {x.get('fiyat', 0):g}"
    return metin


def bb_donustur(df, gorsel_map, barkod_map, kampanya_map=None):
    """BuyBox Sheet verisini tasarim.buybox_tablosu'nun beklediği satır listesine çevirir."""
    satirlar = []
    _kampanya_aktif = hafta_sonu_mu()
    for _, r in df.iterrows():
        kod = str(r.get("Ürün Kodu", "") or "").strip()
        ad = " ".join(str(r.get("Ürün Adı", "") or "").split())
        grup = str(r.get("Alt Grup", "") or "").strip()
        barkod = str(barkod_map.get(kod, "") or "").strip()
        if barkod.endswith(".0"):
            barkod = barkod[:-2]

        def rakip(on_ek):
            fiyat = _sayi(r.get(f"{on_ek} Rakip Fiyat_fiyat"))
            if fiyat is None:
                return None
            return {"ad": str(r.get(f"{on_ek} En Ucuz Rakip", "") or "").strip(), "fiyat": fiyat,
                    "link": (str(r.get(f"{on_ek} Rakip Fiyat_link", "") or "").strip() or None)}

        durum = str(r.get("Durum", "") or "").strip()
        fark_y = _sayi(r.get("Fark (%)"))
        inilecek = durum == "BuyBox için in"
        satirlar.append({
            "kod": kod, "tam_ad": ad, "grup": grup, "barkod": barkod, "gorsel": str(gorsel_map.get(kod, "") or ""),
            "tsf": _sayi(r.get("Tavsiye Fiyat")), "ty": rakip("TY"), "hb": rakip("HB"),
            "kampanya": _sayi((kampanya_map or {}).get(kod)), "kampanya_aktif": _kampanya_aktif,
            "oneri": _sayi(r.get("Önerilen BuyBox Fiyatı")), "durum": durum,
            "fark_tl": _sayi(r.get("Fark (TL)")), "fark_yuzde": fark_y,
            "ty_sira": _siralama_oku(r.get("TY BuyBox Sıralaması")),
            "hb_sira": _siralama_oku(r.get("HB BuyBox Sıralaması")),
            "ty_okuma": str(r.get("TY Okuma", "") or "").strip(),
            "hb_okuma": str(r.get("HB Okuma", "") or "").strip(),
            "ty_bb": str(r.get("TY BuyBox Sahibi", "") or "").strip(),
            "hb_bb": str(r.get("HB BuyBox Sahibi", "") or "").strip(),
            "inilecek": inilecek, "buyuk": inilecek and fark_y is not None and fark_y <= -BUYUK_SAPMA_YUZDE,
            "_arama": " ".join((ad, kod, barkod, grup)).casefold(),
        })
    return satirlar


def _bb_excel_verisi(satirlar):
    kayit = []
    for s in satirlar:
        kayit.append({
            "Barkod": s["barkod"], "Ürün Kodu": s["kod"], "Ürün Adı": s["tam_ad"], "Alt Grup": s["grup"],
            "TSF": s["tsf"], "Kampanya Fiyatı": s.get("kampanya"),
            "TY En Ucuz Rakip": (s["ty"] or {}).get("ad", ""), "TY Rakip Fiyat": (s["ty"] or {}).get("fiyat"),
            "HB En Ucuz Rakip": (s["hb"] or {}).get("ad", ""), "HB Rakip Fiyat": (s["hb"] or {}).get("fiyat"),
            "Önerilen BuyBox Fiyatı": s["oneri"], "Fark (TL)": s["fark_tl"], "Fark (%)": s["fark_yuzde"],
            "Durum": s["durum"], "TY BuyBox Sahibi": s["ty_bb"], "HB BuyBox Sahibi": s["hb_bb"],
            "TY BuyBox Sırası": _siralama_metni(s["ty_sira"]), "HB BuyBox Sırası": _siralama_metni(s["hb_sira"]),
        })
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame(kayit).to_excel(w, index=False, sheet_name="BuyBox")
    return out.getvalue()


def buybox_sayfasi():
    df, zaman = load_buybox()
    tasarim.bb_baslik(zaman.replace("Son Güncelleme: ", "") if zaman else "", BUYUK_SAPMA_YUZDE)
    gun_bandi_goster()
    tasarim.veri_uyarilari(None, tarama_yasi_dk(zaman), BB_GECIKME_ESIGI_DK)
    if df is None or df.empty:
        st.warning("Henüz BuyBox verisi yok. Bilgisayarda buybox_script.py çalıştıktan sonra burada görünecek.")
        return

    fiyat_df, _ = load_data()
    gorsel_map, barkod_map, kampanya_map = {}, {}, {}
    if fiyat_df is not None and "Ürün Kodu" in fiyat_df.columns:
        kodlar = [str(k).strip() for k in fiyat_df["Ürün Kodu"]]
        if "Görsel" in fiyat_df.columns:
            gorsel_map = {k: v for k, v in zip(kodlar, fiyat_df["Görsel"]) if v}
        if "Barkod" in fiyat_df.columns:
            barkod_map = {k: v for k, v in zip(kodlar, fiyat_df["Barkod"]) if v}
        if "Kampanya Fiyatı" in fiyat_df.columns:
            kampanya_map = {k: v for k, v in zip(kodlar, fiyat_df["Kampanya Fiyatı"]) if _sayi(v)}
    satirlar = bb_donustur(df, gorsel_map, barkod_map, kampanya_map)

    c1, c2, c_yenile, c3 = st.columns([2.2, 2.2, 0.9, 1])
    with c1:
        ara = st.text_input("Ürün ara", placeholder="Ürün adı, kodu ya da barkod", key="bb_ara")
    with c2:
        gruplar = sorted({s["grup"] for s in satirlar if s["grup"]})
        secilen = st.multiselect("Alt Grup", gruplar, placeholder="Tümü", key="bb_grup")
    if ara and ara.strip():
        aranan = ara.strip().casefold()
        satirlar = [s for s in satirlar if aranan in s["_arama"]]
    if secilen:
        satirlar = [s for s in satirlar if s["grup"] in secilen]
    with c_yenile:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Verileri yenile", key="bb_yenile", help="Elle tarama yaptıysan 3 dakikalık önbelleği beklemeden güncel veriyi getirir"):
            st.cache_data.clear()
            st.rerun()
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        zaman_ek = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d-%m-%Y_%H-%M")
        st.download_button("📥 Excel'e Aktar", _bb_excel_verisi(satirlar), f"BuyBox_Onerisi_{zaman_ek}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bb_excel")

    tasarim.bb_govde(satirlar, ESIK_YUZDE, BUYUK_SAPMA_YUZDE, kampanya_etiketi=kampanya_etiketi())


# ================= YORUM ANALİZİ =================
@st.cache_data(ttl=180)
def load_yorumlar():
    """(ozet_df, yorum_df, zaman) — yorum_script.py'nin yazdığı iki sayfa."""
    client = get_gspread_client()
    if not client:
        return None, None, ""
    try:
        sh = _tablo_ac(client)
        # UNFORMATTED: sayilar Sheet'in dil ayarindan bagimsiz gelsin (4,33 / 4.33 karisikligi olmasin)
        oz = sh.worksheet(YORUM_OZET_WORKSHEET).get_all_values(value_render_option="UNFORMATTED_VALUE")
        yo = sh.worksheet(YORUM_WORKSHEET).get_all_values(value_render_option="UNFORMATTED_VALUE")
        oz = [["" if v is None else str(v) for v in r] for r in oz]
        yo = [["" if v is None else str(v) for v in r] for r in yo]
    except gspread.WorksheetNotFound:
        return None, None, ""
    except Exception as e:
        st.error(f"Yorum verisi okunurken hata: {e}")
        return None, None, ""
    if not oz or len(oz) < 2:
        return None, None, ""
    zaman = next((h for h in oz[0] if str(h).startswith("Son Güncelleme")), "")
    bas = [h for h in oz[0] if h and not str(h).startswith("Son Güncelleme")]
    ozet = pd.DataFrame([r[:len(bas)] for r in oz[1:]], columns=bas)
    yorum = pd.DataFrame(yo[1:], columns=yo[0]) if yo and len(yo) > 1 else pd.DataFrame(columns=yo[0] if yo else [])
    return ozet, yorum, zaman


def _temalar(deger):
    return [t.strip() for t in str(deger or "").split(";") if t.strip()]


def _yorum_kayitlari(yorum_df):
    kayit = []
    for _, r in yorum_df.iterrows():
        tarih = str(r.get("Tarih", "") or "")
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", tarih)
        kayit.append({
            "kod": str(r.get("Ürün Kodu", "") or "").strip(), "ad": str(r.get("Ürün Adı", "") or "").strip(),
            "grup": str(r.get("Alt Grup", "") or "").strip(), "platform": str(r.get("Platform", "") or "").strip(),
            "tarih": tarih, "tarih_metni": f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else "",
            "puan": _sayi(r.get("Puan")), "satici": str(r.get("Satıcı", "") or "").strip(),
            "braun": str(r.get("Braun Shop", "")).strip().lower() == "evet",
            "memnuniyet": _temalar(r.get("Memnuniyet Temaları")), "sikayet": _temalar(r.get("Şikayet Temaları")),
            "metin": str(r.get("Yorum", "") or ""),
        })
    return kayit


def _tema_sayimi(kayitlar, alan):
    from collections import Counter
    sayac = Counter(t for k in kayitlar for t in k[alan])
    return sayac


def _tema_listesi(sayac):
    """Ürün temaları önce, sonra satıcı & kargo; her grupta çoktan aza."""
    try:
        from yorum_temalari import tema_gruplari
        gruplar = tema_gruplari()
    except Exception:
        gruplar = {}
    sira = {"Ürün": 0, "Satıcı & Kargo": 1}
    liste = [{"tema": t, "grup": gruplar.get(t, "Diğer"), "adet": n} for t, n in sayac.items()]
    return sorted(liste, key=lambda x: (sira.get(x["grup"], 2), -x["adet"]))


def _yorum_excel(satirlar, kayitlar, platform):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame([{
            "Platform": platform, "Ürün Kodu": s["kod"], "Ürün Adı": s["tam_ad"], "Alt Grup": s["grup"],
            "Puan": s["puan"], "Değerlendirme": s["toplam"], "Yazılı Yorum": s["yorumlu"],
            "Haftalık Ortalama Yorum": round(s["haftalik"], 1) if s["haftalik"] is not None else None,
            "Son Yorumlar Ortalama": round(s["son_ort"], 2) if s["son_ort"] is not None else None,
            "Okunan Yorum": s["okunan"],
            "Şikayet Oranı (%)": round(s["sikayet_orani"], 1) if s["sikayet_orani"] is not None else None,
            "En Sık Şikayetler": ", ".join(f"{t} ({n})" for t, n in s["sikayetler"][:3]),
            "En Çok Beğenilenler": ", ".join(f"{t} ({n})" for t, n in s["memnuniyetler"][:3]),
            "Link": s["link"],
        } for s in satirlar]).to_excel(w, index=False, sheet_name="Ürün Özeti")
        pd.DataFrame([{
            "Ürün Kodu": k["kod"], "Tarih": k["tarih_metni"], "Puan": k["puan"],
            "Satıcı": k["satici"], "Braun Shop": "Evet" if k["braun"] else "Hayır",
            "Şikayet Temaları": ", ".join(k["sikayet"]), "Memnuniyet Temaları": ", ".join(k["memnuniyet"]),
            "Yorum": k["metin"],
        } for k in kayitlar]).to_excel(w, index=False, sheet_name="Yorumlar")
    return out.getvalue()


def _json_oku(v, varsayilan):
    try:
        return json.loads(v) if v else varsayilan
    except (ValueError, TypeError):
        return varsayilan


def _haftalik_seri(haftalik: dict, kapsam: str):
    """{'2026-10-26': 4, ...} -> [(hafta, adet|None)], kapsam öncesi haftalar None (bilinmiyor)."""
    seri = []
    for h in sorted(haftalik):
        bilinmiyor = bool(kapsam) and (datetime.strptime(h, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d") < kapsam
        seri.append((h, None if bilinmiyor else int(haftalik[h] or 0)))
    return seri


def _haftalik_ortalama(seri):
    """Tamamlanmış haftaların ortalaması (içinde bulunulan yarım hafta hariç)."""
    tam = [n for h, n in seri[:-1] if n is not None]
    return sum(tam) / len(tam) if tam else None


def _hiz_grafigi(seri, renk: str, baslik: str):
    import altair as alt
    df = pd.DataFrame([{"Hafta": datetime.strptime(h, "%Y-%m-%d"), "Yorum": n,
                        "Etiket": datetime.strptime(h, "%Y-%m-%d").strftime("%d.%m"),
                        "Durum": "Bu hafta (devam ediyor)" if i == len(seri) - 1 else "Tamamlanan hafta"}
                       for i, (h, n) in enumerate(seri) if n is not None])
    if df.empty:
        st.markdown('<div class="yt-bos">Bu seçim için haftalık yorum verisi yok.</div>', unsafe_allow_html=True)
        return
    ort = _haftalik_ortalama(seri)
    taban = alt.Chart(df).encode(x=alt.X("Etiket:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelColor="#6A7E72")))
    cubuk = taban.mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=26).encode(
        y=alt.Y("Yorum:Q", title=None, axis=alt.Axis(grid=True, gridColor="#EEF3F0", labelColor="#6A7E72", tickMinStep=1)),
        color=alt.Color("Durum:N", scale=alt.Scale(domain=["Tamamlanan hafta", "Bu hafta (devam ediyor)"],
                                                   range=[renk, "#D8DEDA"]), legend=None),
        tooltip=[alt.Tooltip("Etiket:N", title="Hafta başı"), alt.Tooltip("Yorum:Q", title="Yazılı yorum"),
                 alt.Tooltip("Durum:N", title="")])
    yazi = taban.mark_text(dy=-8, fontSize=11, fontWeight="bold", color="#3E4A44").encode(
        y="Yorum:Q", text="Yorum:Q")
    katmanlar = [cubuk, yazi]
    if ort is not None:
        cizgi = alt.Chart(pd.DataFrame({"o": [ort]})).mark_rule(color="#15261D", strokeDash=[5, 4], size=1.5).encode(y="o:Q")
        katmanlar.append(cizgi)
    st.altair_chart(alt.layer(*katmanlar).properties(height=240, title=alt.TitleParams(baslik, anchor="start",
                    fontSize=13, color="#15261D")).configure_view(strokeWidth=0).configure(background="#FFFFFF"),
                    use_container_width=True, theme=None)


def yorum_sayfasi():
    ozet_df, yorum_df, zaman = load_yorumlar()
    tasarim.yorum_baslik(_tarih_metni(zaman).replace(" · ", " ") if zaman else "")
    tasarim.veri_uyarilari(None, tarama_yasi_dk(zaman), YORUM_GECIKME_ESIGI_DK)
    if ozet_df is None or ozet_df.empty:
        st.warning("Henüz yorum verisi yok. Bilgisayarda yorum_script.py çalıştıktan sonra burada görünecek.")
        return

    fiyat_df, _ = load_data()
    gorsel_map = {}
    if fiyat_df is not None and "Ürün Kodu" in fiyat_df.columns and "Görsel" in fiyat_df.columns:
        gorsel_map = {str(k).strip(): v for k, v in zip(fiyat_df["Ürün Kodu"], fiyat_df["Görsel"]) if v}
    tum = _yorum_kayitlari(yorum_df) if yorum_df is not None and not yorum_df.empty else []

    # ---- platform seçimi (iki platform ayrı ayrı gösterilir) ----
    platform = st.segmented_control("Platform", ["Trendyol", "Hepsiburada"], default="Trendyol", key="yr_platform",
                                    label_visibility="collapsed") or "Trendyol"
    renk = tasarim.platform_temasi(platform)

    c2, c3, c4, c_yenile, c5 = st.columns([1.6, 1.8, 1.6, 0.9, 1])
    with c_yenile:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Verileri yenile", key="yr_yenile",
                     help="Tarama yeni bittiyse 3 dakikalık önbelleği beklemeden güncel veriyi getirir"):
            st.cache_data.clear()
            st.rerun()
    with c2:
        satici = st.segmented_control("Satıcı", ["Tüm satıcılar", "Braun Shop"], default="Tüm satıcılar",
                                      key="yr_satici", help="Braun Shop: sadece Braun Shop'tan alan müşterilerin yorumları. "
                                      "Puan ve değerlendirme sayısı her zaman ürünün tamamıdır (tüm satıcılar).") or "Tüm satıcılar"
    with c3:
        ara = st.text_input("Ürün ara", placeholder="Ürün adı ya da kodu", key="yr_ara")
    with c4:
        gruplar = sorted({str(g) for g in ozet_df.get("Alt Grup", []) if str(g).strip()})
        secilen = st.multiselect("Alt Grup", gruplar, placeholder="Tümü", key="yr_grup")

    ozet = ozet_df[ozet_df["Platform"] == platform].copy()
    if secilen:
        ozet = ozet[ozet["Alt Grup"].isin(secilen)]
    if ara and ara.strip():
        a = ara.strip().casefold()
        ozet = ozet[(ozet["Ürün Adı"].str.casefold().str.contains(a, regex=False))
                    | (ozet["Ürün Kodu"].str.casefold().str.contains(a, regex=False))]
    kodlar = set(ozet["Ürün Kodu"])
    kayitlar = [k for k in tum if k["kod"] in kodlar and k["platform"] == platform
                and (satici != "Braun Shop" or k["braun"])]

    # ---- ürün satırları ----
    satirlar = []
    for _, x in ozet.iterrows():
        kod = str(x.get("Ürün Kodu", "")).strip()
        uk = [k for k in kayitlar if k["kod"] == kod]
        pu = [k["puan"] for k in uk if k["puan"] is not None]
        ilanlar = _json_oku(x.get("İlanlar"), [])
        link = str(x.get("Link", "") or "").strip()
        if ilanlar:     # en çok değerlendirilen ilan ana link
            link = max(ilanlar, key=lambda i: i.get("toplam") or 0).get("link") or link
        seri = _haftalik_seri(_json_oku(x.get("Haftalık Yorum"), {}), str(x.get("Kapsam Başlangıç", "") or ""))
        satirlar.append({
            "kod": kod, "tam_ad": str(x.get("Ürün Adı", "")), "grup": str(x.get("Alt Grup", "")),
            "gorsel": str(gorsel_map.get(kod, "") or ""), "link": link, "ilanlar": ilanlar,
            "puan": _sayi(x.get("Ortalama Puan")), "toplam": _sayi(x.get("Toplam Değerlendirme")),
            "yorumlu": _sayi(x.get("Yorumlu Değerlendirme")), "durum": str(x.get("Durum", "") or ""),
            "seri": seri, "haftalik": _haftalik_ortalama(seri), "kapsam": str(x.get("Kapsam Başlangıç", "") or ""),
            "okunan": len(uk), "son_ort": sum(pu) / len(pu) if pu else None,
            "dagilim": {y: sum(1 for p in pu if int(p) == y) for y in (1, 2, 3, 4, 5)},
            "sikayet_orani": sum(1 for k in uk if k["sikayet"]) / len(uk) * 100 if uk else None,
            "sikayetler": _tema_sayimi(uk, "sikayet").most_common(3),
            "memnuniyetler": _tema_sayimi(uk, "memnuniyet").most_common(3),
            "sikayet_say": dict(_tema_sayimi(uk, "sikayet")), "memnun_say": dict(_tema_sayimi(uk, "memnuniyet")),
        })
    link_map = {s["kod"]: s["link"] for s in satirlar}
    for k in kayitlar:
        k["link"] = link_map.get(k["kod"], "")

    # ---- KPI ----
    toplam = sum(s["toplam"] or 0 for s in satirlar)
    agirlik = sum((s["toplam"] or 0) * (s["puan"] or 0) for s in satirlar if s["puan"] is not None)
    yorumlu = [s["yorumlu"] for s in satirlar if s["yorumlu"] is not None]
    hizlar = [s["haftalik"] for s in satirlar if s["haftalik"] is not None]
    sikayetli = sum(1 for k in kayitlar if k["sikayet"])
    puanlar = [k["puan"] for k in kayitlar if k["puan"] is not None]
    tasarim.yorum_platform_bandi(platform, len(satirlar))
    tasarim.yorum_kpi({
        "toplam": toplam,
        "toplam_alt": (f"{int(sum(yorumlu)):,} yazılı yorum".replace(",", ".") if yorumlu
                       else "yıldızlı + yorumlu tüm değerlendirmeler") + " · tüm satıcılar",
        "ortalama": agirlik / toplam if toplam else None,
        "ortalama_alt": "Değerlendirme sayısına göre ağırlıklı" + (
            f" · son yorumlarda {sum(puanlar) / len(puanlar):.2f}".replace(".", ",") if puanlar else ""),
        "hiz": sum(hizlar) if hizlar else None,
        "hiz_alt": f"Son {len(satirlar[0]['seri']) - 1 if satirlar and satirlar[0]['seri'] else 11} tamamlanan haftanın ortalaması",
        "sikayet_orani": sikayetli / len(kayitlar) * 100 if kayitlar else None,
        "sikayet_alt": f"{sikayetli} / {len(kayitlar)} yorum" + (" · Braun Shop" if satici == "Braun Shop" else ""),
    })

    # ---- tema panelleri + harita ----
    tasarim.tema_panelleri(_tema_listesi(_tema_sayimi(kayitlar, "sikayet")),
                           _tema_listesi(_tema_sayimi(kayitlar, "memnuniyet")), len(kayitlar))
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    tum_temalar = []
    for alan in ("sikayet", "memnuniyet"):
        for t in _tema_listesi(_tema_sayimi(kayitlar, alan)):
            if t["tema"] not in [y["tema"] for y in tum_temalar]:
                tum_temalar.append({"tema": t["tema"], "grup": t["grup"]})
    sira = {"Ürün": 0, "Satıcı & Kargo": 1}
    sik_say = _tema_sayimi(kayitlar, "sikayet")
    tum_temalar.sort(key=lambda t: (sira.get(t["grup"], 2), -sik_say.get(t["tema"], 0)))
    tasarim.tema_isi_haritasi(satirlar, tum_temalar)
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ---- ürün tablosu ----
    satirlar.sort(key=lambda s: -(s["toplam"] or 0))
    with c5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        zaman_ek = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d-%m-%Y")
        st.download_button("📥 Excel'e Aktar", _yorum_excel(satirlar, kayitlar, platform),
                           f"Yorum_Analizi_{platform}_{zaman_ek}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="yr_excel")
    tasarim.yorum_urun_tablosu(satirlar, platform)
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ---- yorum hızı ----
    with st.container(key="pt_yorum_hiz"):
        st.markdown('<div class="yt-head"><span class="ttl">Yorum hızı</span><span>Haftalık yazılı yorum sayısı · '
                    'kesikli çizgi: tamamlanan haftaların ortalaması</span></div>', unsafe_allow_html=True)
        h1, h2 = st.columns([1.6, 1], gap="large")
        with h2:
            secenek = ["Tüm ürünler"] + [s["kod"] for s in satirlar]
            secim_h = st.selectbox("Ürün", secenek, key="yr_hiz_urun")
            tasarim.hiz_siralamasi(satirlar)
        with h1:
            if secim_h == "Tüm ürünler":
                birlesik = {}
                eksik = 0
                for s in satirlar:
                    for h, n in s["seri"]:
                        if n is None:
                            eksik += 1
                            continue
                        birlesik[h] = birlesik.get(h, 0) + n
                seri = sorted(birlesik.items())
                _hiz_grafigi(seri, renk["ana"], f"{platform} · tüm ürünler")
                kesik = [s["kod"] for s in satirlar if s["kapsam"]]
                if kesik:
                    st.caption("Not: " + ", ".join(kesik) + " çok yorum aldığı için en eski haftaları okunamadı; "
                               "o haftalar toplamda eksik görünebilir.")
            else:
                s = next(x for x in satirlar if x["kod"] == secim_h)
                _hiz_grafigi(s["seri"], renk["ana"], f"{platform} · {secim_h}")
                if s["kapsam"]:
                    st.caption(f"{secim_h} çok yorum aldığı için {s['kapsam']} öncesi okunmadı (gri değil, boş görünür).")
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ---- örnek yorumlar ----
    with st.container(key="pt_yorum_ornek"):
        st.markdown('<div class="yt-head"><span class="ttl">Yorumları oku</span><span>Seçtiğin temaya göre en yeni yorumlar</span></div>',
                    unsafe_allow_html=True)
        sikayet_tema = [x["tema"] for x in _tema_listesi(_tema_sayimi(kayitlar, "sikayet"))]
        memnun_tema = [x["tema"] for x in _tema_listesi(_tema_sayimi(kayitlar, "memnuniyet"))]
        secenekler = (["Tüm yorumlar", "Düşük puanlılar (1-2 ★)"] + [f"Şikayet · {t}" for t in sikayet_tema]
                      + [f"Memnuniyet · {t}" for t in memnun_tema])
        d1, d2, d3 = st.columns([2.2, 1.6, 1])
        with d1:
            secim = st.selectbox("Tema", secenekler, index=2 if len(secenekler) > 2 else 0, key="yr_tema")
        with d2:
            urun_sec = st.selectbox("Ürün", ["Tüm ürünler"] + [s["kod"] for s in satirlar], key="yr_urun")
        with d3:
            adet = st.selectbox("Göster", [10, 25, 50, 100], key="yr_adet")
        liste = kayitlar
        if urun_sec != "Tüm ürünler":
            liste = [k for k in liste if k["kod"] == urun_sec]
        if secim.startswith("Şikayet · "):
            liste = [k for k in liste if secim[10:] in k["sikayet"]]
        elif secim.startswith("Memnuniyet · "):
            liste = [k for k in liste if secim[13:] in k["memnuniyet"]]
        elif secim.startswith("Düşük"):
            liste = [k for k in liste if k["puan"] is not None and k["puan"] <= 2]
        liste = sorted(liste, key=lambda k: k["tarih"], reverse=True)
        st.caption(f"{len(liste)} yorum")
        tasarim.ornek_yorum_listesi(liste[:adet])


# ================= SAYFA =================
tasarim.tema_uygula()
for _kanal in KANALLAR:
    _src = dosyadan_data_uri(PLATFORM_LOGO_DOSYALARI.get(_kanal, "")) or KANAL_LOGO_ADRESLERI.get(_kanal, "")
    if _src:
        # Braunshop logosu sitenin koyu alt bandından geliyor; beyaz zeminde görünsün diye koyulaştırılıyor
        _stil = "max-width:120px;object-fit:contain" + (";filter:brightness(0)" if _kanal == "Braunshop" else "")
        tasarim.KANAL_LOGOLARI[_kanal] = (f'<img src="{_src}" height="22" alt="{_kanal}" '
                                         f'referrerpolicy="no-referrer" style="{_stil}">')

FIYAT_SEKMESI, BUYBOX_SEKMESI = ":material/bar_chart: Ürün Takibi", ":material/shopping_cart: BuyBox"
YORUM_SEKMESI = ":material/reviews: Yorum Analizi"


def _tarih_metni(guncelleme):
    """'Son Güncelleme: 28.09.2026 12:00 (Pazartesi)' -> '28.09.2026 · 12:00'"""
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", str(guncelleme or ""))
    return f"{m.group(1)} · {m.group(2)}" if m else ""


_df_fiyat, _guncelleme = load_data()
_yas = tarama_yasi_dk(_guncelleme)

def _son_tarama(aktif):
    """Üst karttaki 'son tarama' bilgisi açık olan sekmenin kendi taramasıdır (fiyat: saat başı, BuyBox: günlük)."""
    if aktif == BUYBOX_SEKMESI:
        _, bb_zaman = load_buybox()
        bb_yas = tarama_yasi_dk(bb_zaman)
        return _tarih_metni(bb_zaman), (bb_yas is None or bb_yas <= BB_GECIKME_ESIGI_DK), "Son BuyBox taraması"
    if aktif == YORUM_SEKMESI:
        _, _, y_zaman = load_yorumlar()
        y_yas = tarama_yasi_dk(y_zaman)
        return _tarih_metni(y_zaman), (y_yas is None or y_yas <= YORUM_GECIKME_ESIGI_DK), "Son yorum taraması"
    return _tarih_metni(_guncelleme), (_yas is None or _yas <= GECIKME_ESIGI_DK), "Son fiyat taraması"


_aktif = tasarim.ust_baslik([FIYAT_SEKMESI, BUYBOX_SEKMESI, YORUM_SEKMESI], _son_tarama)
if _aktif == BUYBOX_SEKMESI:
    buybox_sayfasi()
elif _aktif == YORUM_SEKMESI:
    yorum_sayfasi()
else:
    fiyat_buybox_sayfasi(_df_fiyat, _yas)
tasarim.alt_bant()
