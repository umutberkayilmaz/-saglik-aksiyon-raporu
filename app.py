import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Sağlık Aksiyon Raporu", page_icon="📊", layout="wide")

GSHEET_NAME = "Saglik_Aksiyon_Guncel"
GSHEET_WORKSHEET = "Guncel"

PLATFORM_COLS = ["Braunshop", "Trendyol", "Hepsiburada", "N11", "İdefix"]

st.markdown("""
<style>
    .block-container { max-width: 100% !important; padding-top: 1.5rem !important; }
    .pill { padding: 4px 12px; border-radius: 20px; font-weight: 600; display: inline-block; }
    .pill-green { background-color: rgba(0, 184, 76, 0.15); color: #00873c; }
    .pill-yellow { background-color: rgba(255, 193, 7, 0.2); color: #8a6500; }
    .pill-red { background-color: rgba(220, 53, 69, 0.15); color: #a71d2a; }
    .update-badge { color: #888; font-size: 12px; background: rgba(128,128,128,0.1); padding: 5px 14px; border-radius: 30px; }
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


@st.cache_data(ttl=180)
def load_data():
    client = get_gspread_client()
    if not client:
        return None, ""

    try:
        sh = client.open(GSHEET_NAME)
        ws = sh.worksheet(GSHEET_WORKSHEET)
        data = ws.get_all_values()
        if not data:
            return None, ""

        update_text = ""
        try:
            update_text = ws.acell("K1").value or ""
        except Exception:
            pass

        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)

        for col in ["Hedef Fiyat"] + PLATFORM_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", ".", regex=False),
                    errors="coerce"
                )

        return df, update_text
    except Exception as e:
        st.error(f"Veri okunurken hata: {e}")
        return None, ""


def price_pill(value, ref):
    if pd.isna(value):
        return "-"
    if pd.isna(ref):
        return f"{value:,.2f} TL"
    if value == ref:
        cls = "pill-green"
    elif value > ref:
        cls = "pill-yellow"
    else:
        cls = "pill-red"
    return f'<span class="pill {cls}">{value:,.2f} TL</span>'


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

    st.caption(f"{len(filtered)} ürün gösteriliyor ({len(df)} toplam)")

    display_df = filtered.copy()
    for col in PLATFORM_COLS:
        if col in display_df.columns:
            display_df[col] = display_df.apply(
                lambda r: price_pill(r[col], r.get("Hedef Fiyat")), axis=1
            )
    if "Hedef Fiyat" in display_df.columns:
        display_df["Hedef Fiyat"] = display_df["Hedef Fiyat"].apply(
            lambda v: f"{v:,.2f} TL" if pd.notna(v) else "-"
        )

    show_cols = [c for c in ["Ürün Adı", "Ürün Kodu", "Alt Grup", "Hedef Fiyat"] + PLATFORM_COLS if c in display_df.columns]
    st.markdown(display_df[show_cols].to_html(escape=False, index=False), unsafe_allow_html=True)

    # ================= EXCEL İNDİRME =================
    tr_time = datetime.utcnow() + timedelta(hours=3)
    excel_name = f"Saglik_Aksiyon_{tr_time.strftime('%d-%m-%Y_%H-%M')}.xlsx"

    export_df = filtered[show_cols].copy() if show_cols else filtered.copy()
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Aksiyon")

    st.download_button("📥 Excel'e Aktar", output.getvalue(), excel_name,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
