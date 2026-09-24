import streamlit as st
import pandas as pd
import re
import io
import os
import base64
import html as _html
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
import tasarim

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık · Fiyat & Buybox", page_icon="📊", layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
GSHEET_WORKSHEET = "Guncel"
BUYBOX_WORKSHEET = "BuyBox"
BUYUK_SAPMA_YUZDE = 15

# ================= PANEL AYARLARI (buradan düzenleyebilirsin) =================
ESIK_YUZDE = 5          # Sarı ile kırmızı arasındaki sınır: TSF'nin %5'ten fazla altındaki fiyatlar kırmızı olur
AKAKCE_GOSTER = True    # TSF sütununun altında Akakçe'deki piyasa en ucuz fiyatı yazsın mı (True / False)
KANALLAR = ["Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]

# Kanal logoları: sitelerin kendi sunucularında kullandıkları güncel, şeffaf logolar.
# Adresi boş olan kanalda logo yerine adı yazar. Repoya aşağıdaki PLATFORM_LOGO_DOSYALARI adlarıyla
# (örn. n11.png, idefix.png) dosya yüklersen, yüklediğin dosya bu adreslerin önüne geçer.
KANAL_LOGO_ADRESLERI = {
    "Braunshop": "https://www.braunshop.com.tr/Data/EditorFiles/braunshop/footer-logo.svg",
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
    .thumb-buyuk img { width: 180px; height: 180px; object-fit: contain; display: block; }
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


def barkod_hucre(barkod, urun_adi):
    b = str(barkod or "").strip()
    if b.endswith(".0"):
        b = b[:-2]
    ad = _html.escape(" ".join(str(urun_adi or "").split()), quote=True)
    if not b:
        return ad or "-"
    return f'<span class="barkod" title="{ad}">{b}</span>'


def thumb_html(url):
    url = str(url or "").strip()
    if not url.startswith("http"):
        return ""
    u = url.replace('"', "&quot;")
    return (f'<div class="thumb"><img src="{u}" referrerpolicy="no-referrer" loading="lazy">'
            f'<div class="thumb-buyuk"><img src="{u}" referrerpolicy="no-referrer" loading="lazy"></div></div>')


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
        sh = client.open(GSHEET_NAME)
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
    except Exception as e:
        st.error(f"Veri okunurken hata: {e}")
        return None, ""


def hafta_sonu_mu():
    return (datetime.now(timezone.utc) + timedelta(hours=3)).weekday() in (4, 5, 6)


def _dolu(v):
    return v is not None and not (isinstance(v, float) and pd.isna(v))


def aktif_referans(tsf, kampanya, braunshop):
    """Cuma-Pazar kampanya fiyati (doluysa), diger gunler TSF; ikisi de yoksa Braunshop fiyati."""
    if hafta_sonu_mu() and _dolu(kampanya):
        return kampanya, "kampanya"
    if _dolu(tsf):
        return tsf, "tsf"
    return (braunshop, "braunshop") if _dolu(braunshop) else (None, "")


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


def fiyat_buybox_sayfasi(df):
    tasarim.baslik(ESIK_YUZDE)
    if df is None or df.empty:
        st.warning("Veri bulunamadı. Google Sheets bağlantısını ve sayfa adını kontrol edin.")
        return
    bb_df, bb_zaman = load_buybox()
    satirlar = veriyi_donustur(df, bb_df)

    c1, c2, c3 = st.columns([2.2, 2.2, 1])
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
    with c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        zaman = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d-%m-%Y_%H-%M")
        st.download_button("📥 Excel'e Aktar", _excel_verisi(satirlar), f"Fiyat_Buybox_{zaman}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="fb_excel")

    notu = (f"BB bilgisi: {bb_zaman.replace('Son Güncelleme: ', '')} BuyBox taraması (Trendyol, Hepsiburada)."
            if bb_zaman else "BB bilgisi perşembe BuyBox taramasından sonra görünür.")
    if hafta_sonu_mu():
        notu += " Hafta sonu: kampanya fiyatı girilmiş ürünler kampanya fiyatına göre karşılaştırılır."
    tasarim.govde(satirlar, ESIK_YUZDE, tablo_notu=notu, klasik=True, akakce_goster=AKAKCE_GOSTER)


# ================= BUYBOX SEKMESİ =================
@st.cache_data(ttl=180)
def load_buybox():
    client = get_gspread_client()
    if not client:
        return None, ""
    try:
        ws = client.open(GSHEET_NAME).worksheet(BUYBOX_WORKSHEET)
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


def gun_bandi():
    gun = (datetime.now(timezone.utc) + timedelta(hours=3)).weekday()
    if gun == 3:
        st.info("📅 **Perşembe: BuyBox hazırlık günü.** Aşağıdaki önerilen fiyatları Trendyol ve Hepsiburada'da uygula. "
                "Fiyatlar Cuma, Cumartesi ve Pazar boyunca geçerli olacak.")
    elif gun in (4, 5, 6):
        st.success("🛒 **BuyBox dönemi (Cuma-Pazar).** Perşembe belirlenen fiyatlar aktif olmalı.")
    elif gun == 0:
        st.warning("↩️ **Pazartesi: tavsiye satış fiyatına dönüş günü.** BuyBox için indirdiğin fiyatları tavsiye fiyata geri çek.")
    else:
        st.info("Normal dönem: tavsiye satış fiyatları geçerli. Bir sonraki BuyBox önerisi Perşembe hazırlanacak.")


def _tl(v):
    return f"{v:,.2f} TL" if v is not None and pd.notna(v) else "-"


def rakip_hucre(ad, fiyat, link):
    if fiyat is None or pd.isna(fiyat):
        return "-"
    fiyat_html = f'<span class="pill pill-plain">{_tl(fiyat)}</span>'
    if link:
        fiyat_html = f'<a class="pill pill-plain" href="{link.replace(chr(34), "&quot;")}" target="_blank">{_tl(fiyat)}</a>'
    return f'<div style="font-size:12px; margin-bottom:4px;">{ad or ""}</div>{fiyat_html}'


def oneri_hucre(oneri, tavsiye, fark_yuzde):
    if oneri is None or pd.isna(oneri):
        return "-"
    if fark_yuzde is not None and pd.notna(fark_yuzde) and fark_yuzde <= -BUYUK_SAPMA_YUZDE:
        return f'<span class="pill pill-red" style="font-size:15px;">⚠️ {_tl(oneri)}</span>'
    if tavsiye is not None and pd.notna(tavsiye) and oneri < tavsiye:
        return f'<span class="pill pill-green" style="font-size:15px;">{_tl(oneri)}</span>'
    return f'<span class="pill pill-plain" style="font-size:15px;">{_tl(oneri)}</span>'


def buybox_sayfasi():
    gun_bandi()
    df, zaman = load_buybox()
    gorsel_map = {}
    fiyat_df, _ = load_data()
    if fiyat_df is not None and "Görsel" in fiyat_df.columns:
        gorsel_map = {str(k).strip(): v for k, v in zip(fiyat_df["Ürün Kodu"], fiyat_df["Görsel"]) if v}
    barkod_map = {}
    if fiyat_df is not None and "Barkod" in fiyat_df.columns:
        barkod_map = {str(k).strip(): v for k, v in zip(fiyat_df["Ürün Kodu"], fiyat_df["Barkod"]) if v}
    if zaman:
        st.markdown(f'<div style="text-align:right;"><span class="update-badge">🔄 Öneri verisi: {zaman.replace("Son Güncelleme: ", "")}</span></div>',
                    unsafe_allow_html=True)

    if df is None or df.empty:
        st.warning("Henüz BuyBox verisi yok. Bilgisayarda buybox_script.py çalıştıktan sonra burada görünecek.")
        return

    inilecek = df[df["Durum"] == "BuyBox için in"] if "Durum" in df.columns else df.iloc[0:0]
    buyuk = inilecek[inilecek["Fark (%)"] <= -BUYUK_SAPMA_YUZDE] if "Fark (%)" in inilecek.columns else inilecek.iloc[0:0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("İnilmesi gereken ürün", len(inilecek))
    m2.metric("TSF'de kalacak", len(df) - len(inilecek))
    m3.metric("Ortalama indirim", f"-%{abs(inilecek['Fark (%)'].mean()):.1f}".replace(".", ",") if len(inilecek) else "-")
    m4.metric(f"Büyük sapma (%{BUYUK_SAPMA_YUZDE}+)", len(buyuk))

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        ara = st.text_input("🔍 Ürün Ara...", key="bb_ara")
    with c2:
        gruplar = sorted([g for g in df.get("Alt Grup", pd.Series(dtype=str)).dropna().unique() if g])
        grup = st.multiselect("📂 Alt Grup", gruplar, placeholder="Tümü", key="bb_grup")
    with c3:
        filtre = st.selectbox("🎯 Göster", ["Tümü", "Sadece inilecekler", "Sadece büyük sapmalar"], key="bb_filtre")

    f = df.copy()
    if ara:
        f = f[f.apply(lambda r: r.astype(str).str.contains(ara, case=False).any(), axis=1)]
    if grup:
        f = f[f["Alt Grup"].isin(grup)]
    if filtre == "Sadece inilecekler":
        f = f[f["Durum"] == "BuyBox için in"]
    elif filtre == "Sadece büyük sapmalar":
        f = f[(f["Durum"] == "BuyBox için in") & (f["Fark (%)"] <= -BUYUK_SAPMA_YUZDE)]

    st.caption(f"{len(f)} ürün gösteriliyor · Öneri = Braun Shop dışındaki en ucuz stoklu rakibin en az 10 TL altı, "
               f"sonu 9 ile biten fiyat · ⚠️ = tavsiye fiyatından %{BUYUK_SAPMA_YUZDE} veya daha fazla aşağıda")

    satirlar = []
    for _, r in f.iterrows():
        fark_tl, fark_y = r.get("Fark (TL)"), r.get("Fark (%)")
        fark_metni = "-"
        if fark_tl is not None and pd.notna(fark_tl) and fark_tl != 0:
            fark_metni = f"{fark_tl:,.0f} TL<br><small>{'-' if fark_y < 0 else '+'}%{abs(fark_y):.1f}</small>".replace(".", ",")
        satirlar.append({
            "Görsel": thumb_html(gorsel_map.get(str(r.get("Ürün Kodu", "")).strip())),
            "Barkod": barkod_hucre(barkod_map.get(str(r.get("Ürün Kodu", "")).strip()), r.get("Ürün Adı")),
            "Ürün Kodu": r.get("Ürün Kodu", ""),
            "TSF": _tl(r.get("Tavsiye Fiyat")),
            "Trendyol En Ucuz Rakip": rakip_hucre(r.get("TY En Ucuz Rakip"), r.get("TY Rakip Fiyat_fiyat"), r.get("TY Rakip Fiyat_link")),
            "Hepsiburada En Ucuz Rakip": rakip_hucre(r.get("HB En Ucuz Rakip"), r.get("HB Rakip Fiyat_fiyat"), r.get("HB Rakip Fiyat_link")),
            "Önerilen BuyBox Fiyatı": oneri_hucre(r.get("Önerilen BuyBox Fiyatı"), r.get("Tavsiye Fiyat"), fark_y),
            "Fark": fark_metni,
            "Durum": r.get("Durum", ""),
            "BuyBox Sahibi (TY / HB)": f'{r.get("TY BuyBox Sahibi", "") or "-"}<br>{r.get("HB BuyBox Sahibi", "") or "-"}',
        })
    if satirlar:
        st.markdown(pd.DataFrame(satirlar).to_html(escape=False, index=False, classes="rapor-tablo"),
                    unsafe_allow_html=True)

    tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
    disa = ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Tavsiye Fiyat", "TY En Ucuz Rakip", "TY Rakip Fiyat_fiyat",
            "HB En Ucuz Rakip", "HB Rakip Fiyat_fiyat", "En Ucuz Rakip Fiyat", "Önerilen BuyBox Fiyatı",
            "Fark (TL)", "Fark (%)", "Durum", "TY BuyBox Sahibi", "HB BuyBox Sahibi"]
    ex = f[[c for c in disa if c in f.columns]].rename(columns={"Tavsiye Fiyat": "TSF",
                                                                "TY Rakip Fiyat_fiyat": "TY Rakip Fiyat",
                                                                "HB Rakip Fiyat_fiyat": "HB Rakip Fiyat"})
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        ex.to_excel(w, index=False, sheet_name="BuyBox")
    st.download_button("📥 BuyBox Önerilerini Excel'e Aktar", out.getvalue(),
                       f"BuyBox_Onerisi_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bb_excel")


# ================= SAYFA =================
tasarim.tema_uygula()
for _kanal in KANALLAR:
    _src = dosyadan_data_uri(PLATFORM_LOGO_DOSYALARI.get(_kanal, "")) or KANAL_LOGO_ADRESLERI.get(_kanal, "")
    if _src:
        # Braunshop logosu sitenin koyu alt bandından geliyor; beyaz zeminde görünsün diye koyulaştırılıyor
        _stil = "max-width:120px;object-fit:contain" + (";filter:brightness(0)" if _kanal == "Braunshop" else "")
        tasarim.KANAL_LOGOLARI[_kanal] = (f'<img src="{_src}" height="22" alt="{_kanal}" '
                                         f'referrerpolicy="no-referrer" style="{_stil}">')

_df_fiyat, _guncelleme = load_data()
_son = _guncelleme.replace("Son Güncelleme:", "").strip().replace(" ", " · ", 1) if _guncelleme else ""
tasarim.ust_bant(_son)
sekme_fiyat, sekme_buybox = st.tabs(["📊 Fiyat & Buybox Takibi", "🛒 BuyBox Önerisi"])
with sekme_fiyat:
    fiyat_buybox_sayfasi(_df_fiyat)
with sekme_buybox:
    buybox_sayfasi()
tasarim.alt_bant()
