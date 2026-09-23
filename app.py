import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık Aksiyon Raporu", page_icon="📊", layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
GSHEET_WORKSHEET = "Guncel"
BUYBOX_WORKSHEET = "BuyBox"
BUYUK_SAPMA_YUZDE = 15

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
</style>
""", unsafe_allow_html=True)


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

        update_text = ""
        try:
            update_text = ws.acell("N1").value or ""
        except Exception:
            pass

        headers = values[0]
        rows = values[1:]
        formula_rows = formulas[1:]

        df = pd.DataFrame(rows, columns=headers)
        df_formula = pd.DataFrame(formula_rows, columns=headers)

        for col in ["Hedef Fiyat", "En Düşük Fiyat"]:
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

        st.caption(f"{len(filtered)} ürün gösteriliyor ({len(df)} toplam) — 🏆 = Trendyol/Hepsiburada arasındaki en düşük fiyat · Akakçe sütunu piyasadaki en ucuz fiyatı ve satıcısını gösterir")

        # ================= TABLO OLUŞTURMA =================
        display_rows = []
        for _, r in filtered.iterrows():
            ref = r.get("Hedef Fiyat")
            en_dusuk = r.get("En Düşük Fiyat")

            row_html = {
                "Ürün Adı": r.get("Ürün Adı", ""),
                "Ürün Kodu": r.get("Ürün Kodu", ""),
                "Alt Grup": r.get("Alt Grup", ""),
                "Hedef Fiyat": f"{ref:,.2f} TL" if pd.notna(ref) else "-",
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
        table_order = ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Hedef Fiyat", "Akakçe", "Akakçe Satıcı",
                       "Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]
        show_cols = [c for c in table_order if c in display_df.columns]
        st.markdown(display_df[show_cols].to_html(escape=False, index=False), unsafe_allow_html=True)

        # ================= EXCEL İNDİRME =================
        tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
        excel_name = f"Saglik_Aksiyon_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx"

        export_map = {"Ürün Adı": "Ürün Adı", "Ürün Kodu": "Ürün Kodu", "Alt Grup": "Alt Grup",
                      "Hedef Fiyat": "Hedef Fiyat", "En Düşük Fiyat": "En Düşük Fiyat",
                      "Akakçe_fiyat": "Akakçe", "Akakçe Satıcı": "Akakçe Satıcı"}
        for c in PLATFORM_COLS:
            if c != "Akakçe":
                export_map[f"{c}_fiyat"] = c
        present = [c for c in export_map if c in filtered.columns]
        export_df = filtered[present].rename(columns=export_map)

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
    m2.metric("Tavsiye fiyatta kalacak", len(df) - len(inilecek))
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
            "Ürün Adı": r.get("Ürün Adı", ""),
            "Ürün Kodu": r.get("Ürün Kodu", ""),
            "Tavsiye Fiyat": _tl(r.get("Tavsiye Fiyat")),
            "Trendyol En Ucuz Rakip": rakip_hucre(r.get("TY En Ucuz Rakip"), r.get("TY Rakip Fiyat_fiyat"), r.get("TY Rakip Fiyat_link")),
            "Hepsiburada En Ucuz Rakip": rakip_hucre(r.get("HB En Ucuz Rakip"), r.get("HB Rakip Fiyat_fiyat"), r.get("HB Rakip Fiyat_link")),
            "Önerilen BuyBox Fiyatı": oneri_hucre(r.get("Önerilen BuyBox Fiyatı"), r.get("Tavsiye Fiyat"), fark_y),
            "Fark": fark_metni,
            "Durum": r.get("Durum", ""),
            "BuyBox Sahibi (TY / HB)": f'{r.get("TY BuyBox Sahibi", "") or "-"}<br>{r.get("HB BuyBox Sahibi", "") or "-"}',
        })
    if satirlar:
        st.markdown(pd.DataFrame(satirlar).to_html(escape=False, index=False), unsafe_allow_html=True)

    tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
    disa = ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Tavsiye Fiyat", "TY En Ucuz Rakip", "TY Rakip Fiyat_fiyat",
            "HB En Ucuz Rakip", "HB Rakip Fiyat_fiyat", "En Ucuz Rakip Fiyat", "Önerilen BuyBox Fiyatı",
            "Fark (TL)", "Fark (%)", "Durum", "TY BuyBox Sahibi", "HB BuyBox Sahibi"]
    ex = f[[c for c in disa if c in f.columns]].rename(columns={"TY Rakip Fiyat_fiyat": "TY Rakip Fiyat",
                                                                "HB Rakip Fiyat_fiyat": "HB Rakip Fiyat"})
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        ex.to_excel(w, index=False, sheet_name="BuyBox")
    st.download_button("📥 BuyBox Önerilerini Excel'e Aktar", out.getvalue(),
                       f"BuyBox_Onerisi_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="bb_excel")


# ================= SAYFA =================
st.title("📊 Sağlık Aksiyon Raporu")
sekme_fiyat, sekme_buybox = st.tabs(["📊 Fiyat Takibi", "🛒 BuyBox Önerisi"])
with sekme_fiyat:
    fiyat_takibi_sayfasi()
with sekme_buybox:
    buybox_sayfasi()
