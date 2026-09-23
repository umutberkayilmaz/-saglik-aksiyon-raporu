import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık Aksiyon Raporu", page_icon="📊", layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
GSHEET_WORKSHEET = "Guncel"

PLATFORM_COLS = ["Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]
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
            update_text = ws.acell("L1").value or ""
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


# ================= ANA GÖVDE =================
col_title, col_update = st.columns([3, 1])
with col_title:
    st.title("📊 Sağlık Aksiyon Raporu")

df, update_text = load_data()

with col_update:
    if update_text:
        st.markdown(f'<div style="text-align:right; margin-top: 20px;">'
                    f'<span class="update-badge">🔄 {update_text}</span></div>', unsafe_allow_html=True)

if df is None or df.empty:
    st.warning("Veri bulunamadı. Google Sheets bağlantısını ve sayfa adını kontrol edin.")
else:
    col_search, col_grup = st.columns([2, 2])
    with col_search:
        search = st.text_input("🔍 Ürün Ara...")
    with col_grup:
        gruplar = sorted([g for g in df["Alt Grup"].dropna().unique() if g])
        secilen_grup = st.multiselect("📂 Alt Grup", gruplar, placeholder="Tümü")

    filtered = df.copy()
    if search:
        filtered = filtered[filtered.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
    if secilen_grup:
        filtered = filtered[filtered["Alt Grup"].isin(secilen_grup)]

    st.caption(f"{len(filtered)} ürün gösteriliyor ({len(df)} toplam) — 🏆 rozeti Trendyol/Hepsiburada arasındaki en düşük fiyatı gösterir")

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
        display_rows.append(row_html)

    display_df = pd.DataFrame(display_rows)
    show_cols = [c for c in ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Hedef Fiyat"] + PLATFORM_COLS if c in display_df.columns]
    st.markdown(display_df[show_cols].to_html(escape=False, index=False), unsafe_allow_html=True)

    # ================= EXCEL İNDİRME =================
    tr_time = datetime.utcnow() + timedelta(hours=3)
    excel_name = f"Saglik_Aksiyon_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx"

    export_cols = ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Hedef Fiyat", "En Düşük Fiyat"] + \
                  [f"{c}_fiyat" for c in PLATFORM_COLS]
    export_df = filtered[[c for c in export_cols if c in filtered.columns]].copy()
    export_df.columns = ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Hedef Fiyat", "En Düşük Fiyat"] + PLATFORM_COLS

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Aksiyon")

    st.download_button("📥 Excel'e Aktar", output.getvalue(), excel_name,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
