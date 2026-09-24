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

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık Aksiyon Raporu", page_icon="📊", layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
GSHEET_WORKSHEET = "Guncel"
BUYBOX_WORKSHEET = "BuyBox"
BUYUK_SAPMA_YUZDE = 15

# ================= PANEL SÜTUN AYARLARI (buradan düzenleyebilirsin) =================
# Fiyat Takibi tablosunda hangi sütunların, hangi sırayla görüneceği.
# Bir sütunu gizlemek için satırını sil; sırasını değiştirmek için satırın yerini değiştir.
FIYAT_TABLOSU_SUTUNLARI = [
    "Görsel",
    "Barkod",
    "Ürün Kodu",
    "Alt Grup",
    "TSF",
    "Kampanya Fiyatı",
    "Akakçe",
    "Braunshop",
    "Trendyol",
    "Hepsiburada",
    "N11",
    "İdefix",
]

# Panelde ve Excel çıktısında görünen başlıklar.
# SOLDAKİ isimlere dokunma (sistem bunları kullanıyor); SAĞDAKİ yazıyı istediğin gibi değiştir.
SUTUN_ETIKETLERI = {
    "Görsel": "Görsel",
    "Barkod": "Barkod",
    "Ürün Adı": "Ürün Adı",
    "Ürün Kodu": "Ürün Kodu",
    "Alt Grup": "Alt Grup",
    "TSF": "TSF",
    "Kampanya Fiyatı": "Hafta Sonu Kampanya Fiyatı",
    "En Düşük Fiyat": "En Düşük Fiyat",
    "Akakçe": "Akakçe",
    "Akakçe Satıcı": "Akakçe Satıcı",
    "Braunshop": "Braunshop",
    "Trendyol": "Trendyol",
    "Hepsiburada": "Hepsiburada",
    "N11": "N11",
    "İdefix": "İdefix",
}

# Platform basliklarindaki logolar: GitHub'da repoya (ya da "logos" klasorune) bu adlarla PNG yuklersen
# o logo kullanilir; yuklemezsen sitenin kendi kucuk ikonu ve adi gosterilir.
PLATFORM_LOGO_DOSYALARI = {"Akakçe": "akakce.png", "Braunshop": "braunshop.png", "Trendyol": "trendyol.png",
                           "Hepsiburada": "hepsiburada.png", "N11": "n11.png", "İdefix": "idefix.png"}
PLATFORM_DOMAINLERI = {"Akakçe": "akakce.com", "Braunshop": "braunshop.com.tr", "Trendyol": "trendyol.com",
                       "Hepsiburada": "hepsiburada.com", "N11": "n11.com", "İdefix": "idefix.com"}
PLATFORM_LINKLERI = {
    "Akakçe": "https://www.akakce.com/hesabim/favori-listem/",
    "Braunshop": "https://www.braunshop.com.tr",
    "Trendyol": "https://www.trendyol.com/sr?mid=194191&os=1",
    "Hepsiburada": "https://www.hepsiburada.com/magaza/braun-shop?tab=allproducts",
    "N11": "https://www.n11.com/magaza/braunshop",
    "İdefix": "https://www.idefix.com/satici/braun-shop-1750",
}

PLATFORM_COLS = ["Akakçe", "Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]
LOWEST_SOURCE_COLS = ["Trendyol", "Hepsiburada"]  # "En Dusuk Fiyat" bu ikisinden hesaplaniyor

st.markdown("""
<style>
    .block-container { max-width: 100% !important; padding-top: 1.5rem !important; }
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


def platform_basligi(platform, etiket, urun_sayisi):
    logo = dosyadan_data_uri(PLATFORM_LOGO_DOSYALARI.get(platform, ""))
    if logo:
        icerik = f'<img class="plat-logo" src="{logo}" title="{etiket}">'
    else:
        domain = PLATFORM_DOMAINLERI.get(platform, "")
        ikon = (f'<img class="plat-ikon" src="https://www.google.com/s2/favicons?domain={domain}&sz=64" '
                f'referrerpolicy="no-referrer">' if domain else "")
        icerik = f'{ikon}<span class="plat-ad">{etiket}</span>'
    link = PLATFORM_LINKLERI.get(platform)
    if link:
        icerik = f'<a href="{link}" target="_blank">{icerik}</a>'
    return f'<div class="plat-baslik">{icerik}<div class="plat-sayi">{urun_sayisi} Ürün</div></div>'


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


def price_pill(price, link, ref, is_lowest):
    if price is None or pd.isna(price):
        return "-"

    if ref is not None and not pd.isna(ref):
        if price == ref:
            cls = "pill-green"
        elif price > ref:
            cls = "pill-yellow"
        else:
            cls = "pill-red"
    else:
        cls = "pill-plain"

    extra_cls = " pill-lowest" if is_lowest else ""
    badge = " 🏆" if is_lowest else ""
    text = f"{price:,.2f} TL{badge}"

    if link:
        safe_link = link.replace('"', "&quot;")
        return f'<a class="pill {cls}{extra_cls}" href="{safe_link}" target="_blank">{text}</a>'
    return f'<span class="pill {cls}{extra_cls}">{text}</span>'


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


def fiyat_hucre(v, aktif):
    if not _dolu(v):
        return "-"
    return f"<b>{v:,.2f} TL</b>" if aktif else f"{v:,.2f} TL"


# ================= FİYAT TAKİBİ SEKMESİ =================
def fiyat_takibi_sayfasi():
    df, update_text = load_data()
    if update_text:
        st.markdown(f'<div style="text-align:right;"><span class="update-badge">🔄 {update_text}</span></div>',
                    unsafe_allow_html=True)

    if df is None or df.empty:
        st.warning("Veri bulunamadı. Google Sheets bağlantısını ve sayfa adını kontrol edin.")
    else:
        col_search, col_grup = st.columns([2, 2])
        with col_search:
            search = st.text_input("🔍 Ürün Ara...", key="fiyat_ara")
        with col_grup:
            gruplar = sorted([g for g in df["Alt Grup"].dropna().unique() if g])
            secilen_grup = st.multiselect("📂 Alt Grup", gruplar, placeholder="Tümü", key="fiyat_grup")

        filtered = df.copy()
        if search:
            filtered = filtered[filtered.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
        if secilen_grup:
            filtered = filtered[filtered["Alt Grup"].isin(secilen_grup)]

        bugun_ref = "Hafta Sonu Kampanya Fiyatı'na (doluysa)" if hafta_sonu_mu() else "TSF'ye"
        st.caption(f"{len(filtered)} ürün gösteriliyor ({len(df)} toplam) · Renkler bugün {bugun_ref} göre, "
                   f"kalın yazılı fiyat karşılaştırmada kullanılan fiyattır (ikisi de boşsa Braunshop fiyatı) · "
                   f"🏆 = Trendyol/Hepsiburada arasındaki en düşük fiyat · Akakçe sütunu piyasadaki en ucuz "
                   f"fiyatı gösterir")

        # ================= TABLO OLUŞTURMA =================
        display_rows = []
        for _, r in filtered.iterrows():
            tsf, kampanya = r.get("TSF"), r.get("Kampanya Fiyatı")
            ref, ref_turu = aktif_referans(tsf, kampanya, r.get("Braunshop_fiyat"))
            en_dusuk = r.get("En Düşük Fiyat")

            row_html = {
                "Görsel": thumb_html(r.get("Görsel")),
                "Barkod": barkod_hucre(r.get("Barkod"), r.get("Ürün Adı")),
                "Ürün Adı": r.get("Ürün Adı", ""),
                "Ürün Kodu": f'<span title="{_html.escape(" ".join(str(r.get("Ürün Adı", "")).split()), quote=True)}">'
                             f'{r.get("Ürün Kodu", "")}</span>',
                "Alt Grup": r.get("Alt Grup", ""),
                "TSF": fiyat_hucre(tsf, ref_turu == "tsf"),
                "Kampanya Fiyatı": fiyat_hucre(kampanya, ref_turu == "kampanya"),
            }
            for col in PLATFORM_COLS:
                price = r.get(f"{col}_fiyat")
                link = r.get(f"{col}_link")
                is_lowest = (
                    col in LOWEST_SOURCE_COLS
                    and pd.notna(price) and pd.notna(en_dusuk)
                    and abs(price - en_dusuk) < 0.01
                )
                row_html[col] = price_pill(price, link, ref, is_lowest)
                if col == "Akakçe":
                    satici = r.get("Akakçe Satıcı", "")
                    row_html["Akakçe Satıcı"] = satici if satici else "-"
            display_rows.append(row_html)

        display_df = pd.DataFrame(display_rows)
        show_cols = [c for c in FIYAT_TABLOSU_SUTUNLARI if c in display_df.columns]
        basliklar = {}
        for c in show_cols:
            etiket = SUTUN_ETIKETLERI.get(c, c)
            if c in PLATFORM_COLS:
                sayi = int(filtered[f"{c}_fiyat"].notna().sum()) if f"{c}_fiyat" in filtered.columns else 0
                basliklar[c] = platform_basligi(c, etiket, sayi)
            else:
                basliklar[c] = etiket
        st.markdown(display_df[show_cols].rename(columns=basliklar)
                    .to_html(escape=False, index=False, classes="rapor-tablo"),
                    unsafe_allow_html=True)

        # ================= EXCEL İNDİRME =================
        tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
        excel_name = f"Saglik_Aksiyon_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx"

        export_map = {"Barkod": "Barkod", "Ürün Adı": "Ürün Adı", "Ürün Kodu": "Ürün Kodu", "Alt Grup": "Alt Grup",
                      "TSF": "TSF", "Kampanya Fiyatı": "Kampanya Fiyatı", "En Düşük Fiyat": "En Düşük Fiyat",
                      "Akakçe_fiyat": "Akakçe", "Akakçe Satıcı": "Akakçe Satıcı"}
        for c in PLATFORM_COLS:
            if c != "Akakçe":
                export_map[f"{c}_fiyat"] = c
        present = [c for c in export_map if c in filtered.columns]
        export_df = filtered[present].rename(columns=export_map).rename(columns=SUTUN_ETIKETLERI)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Aksiyon")

        st.download_button("📥 Excel'e Aktar", output.getvalue(), excel_name,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="fiyat_excel")


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
# Sirket logosu (Sistem). Repoya sistem.png yuklersen o kullanilir.
SISTEM_LOGO_GOMULU = "data:image/png;base64,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"
_sirket_logo = dosyadan_data_uri("sistem.png") or SISTEM_LOGO_GOMULU
st.markdown(f'<div class="sirket-baslik"><img src="{_sirket_logo}" alt="Sistem"><span>Sağlık Aksiyon Raporu</span></div>',
            unsafe_allow_html=True)
sekme_fiyat, sekme_buybox = st.tabs(["📊 Fiyat Takibi", "🛒 BuyBox Önerisi"])
with sekme_fiyat:
    fiyat_takibi_sayfasi()
with sekme_buybox:
    buybox_sayfasi()
