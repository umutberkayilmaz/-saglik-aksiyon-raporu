# -*- coding: utf-8 -*-
"""
Limitli Adet · Akakçe Fiyat Kontrolü  (Sağlık panelinin "Limitli Adet" sekmesi)

B2B sitemizin (Limitli Adet) eczane / geleneksel bayi fiyatlarını Akakçe'deki en düşük
piyasa fiyatıyla karşılaştırır.

Veri kaynağı: Google Sheet (Limitli_Adet_Akakce)
  Akakce      -> bilgisayardaki tarayıcı (akakce_tara.py) yazar: Akakçe listesindeki ürünler ve en düşük fiyat
  Gecmis      -> tarayıcı her gün bir kez ekler
  Limitli     -> bu panelden yüklenen aylık Limitli Adet Excel'i
  Eslestirme  -> EAN <-> Akakçe ürün kodu (bu panelden düzenlenir)
  Durum       -> son tarama, yüklenen ay vb.
"""
import html
import io
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import gspread
import pandas as pd
import streamlit as st


# ================= AYARLAR =================
VARSAYILAN_ESIK = 10        # Akakçe fiyatı bizim fiyatın bu %'den az üstündeyse "marj dar" (sarı)
GECIKME_SAAT = 30           # son Akakçe taraması bundan eskiyse uyarı
TR = timezone(timedelta(hours=3))
# ===========================================

_CSS = """
<style>
.la-baslik { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin:6px 0 10px; }
.la-baslik b { font-size:22px; font-weight:800; color:#10281B; }
.la-baslik span { font-size:13.5px; color:#52675A; }
.la-baslik i.la-ay { font-style:normal; font-size:12.5px; font-weight:700; padding:5px 12px; border-radius:999px; background:#F1F5F3; color:#15261D; }
.la-kpis { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:14px; margin:4px 0 16px; }
.la-kpi { background:#fff; border:1px solid #DCE9E1; border-radius:16px; padding:14px 18px; }
.la-kpi .la-l { font-size:12.5px; font-weight:600; color:#5E7366; }
.la-kpi .la-v { font-size:32px; font-weight:800; color:#10281B; line-height:1.15; }
.la-kpi .la-s { font-size:12px; color:#6A7E72; }
.la-kpi.la-bad { background:#FFF9F8; border-color:#F3CFC8; } .la-kpi.la-bad .la-v { color:#B3291B; }
.la-kpi.la-warn { background:#FFFCF2; border-color:#F0D68E; } .la-kpi.la-warn .la-v { color:#8A5A00; }
.la-kpi.la-ok .la-v { color:#14693A; }
@media (max-width: 900px) { .la-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
.la-kart { background:#fff; border:1px solid #DCE9E1; border-radius:20px; padding:14px 18px; box-shadow:0 6px 24px rgba(20,70,45,.06); overflow-x:auto; }
table.la-t { width:100%; border-collapse:separate !important; border-spacing:0; font-size:13px; color:#15261D; margin:0 !important; }
table.la-t tr { border:0 !important; }
table.la-t th { font-size:11px; font-weight:700; color:#6A7E72; letter-spacing:.05em; text-transform:uppercase; text-align:center !important;
                padding:8px 4px !important; border:0 !important; border-bottom:1px solid #E1EAE4 !important; background:#fff; }
table.la-t th.la-sol, table.la-t td.la-sol { text-align:left !important; }
table.la-t td { padding:6px 4px !important; border:0 !important; border-bottom:1px solid #EEF3F0 !important; text-align:center; vertical-align:middle; }
.la-urun { display:flex; align-items:center; gap:8px; min-width:170px; max-width:230px; }
.la-urun img { width:42px; height:42px; object-fit:contain; background:#fff; border:1px solid #E1EAE4; border-radius:8px; flex-shrink:0; }
.la-urun .la-bos { width:42px; height:42px; border-radius:8px; background:#F1F5F3; flex-shrink:0; display:inline-block; }
.la-urun b { display:block; font-size:12.5px; font-weight:650; line-height:1.3; }
.la-urun small { color:#6A7E72; font-size:11.5px; }
.la-fiyat { font-size:14.5px; font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums; }
.la-alt { display:block; font-size:11px; color:#6A7E72; font-weight:500; white-space:nowrap; text-transform:none; letter-spacing:0; }
.la-hucre { display:inline-flex; flex-direction:column; gap:2px; padding:6px 10px; border-radius:11px; border:1px solid; min-width:96px; }
.la-hucre .la-p { font-size:14.5px; font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums; }
.la-hucre .la-d { font-size:11px; font-weight:700; }
.la-hucre.la-ok   { background:#E6F5EC; border-color:#C3E5D0; color:#14693A; }
.la-hucre.la-warn { background:#FFF5DA; border-color:#F0D68E; color:#7F5300; }
.la-hucre.la-bad  { background:#FDE6E2; border-color:#F3BDB4; color:#A3261A; }
.la-hucre.la-none { background:#F4F6F5; border:1px dashed #C9D3CD; color:#7A8680; font-weight:600; }
a.la-lnk { text-decoration:none !important; color:inherit !important; }
a.la-lnk:hover .la-hucre { box-shadow:0 4px 12px rgba(20,70,45,.14); }
.la-satici { display:flex; align-items:center; justify-content:center; gap:6px; font-size:11.5px; color:#3E4A44; }
.la-satici img { height:16px; max-width:80px; object-fit:contain; }
.la-mini { display:flex; flex-direction:column; align-items:center; gap:1px; padding:4px 8px; border-radius:9px; border:1px solid;
           min-width:70px; margin:2px auto; }
.la-mini .la-me { font-size:10px; font-weight:700; opacity:.75; text-transform:none; }
.la-mini .la-p { font-size:13px; font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums; }
.la-mini .la-d { font-size:10.5px; font-weight:700; }
.la-mini.la-ok { background:#E6F5EC; border-color:#C3E5D0; color:#14693A; }
.la-mini.la-warn { background:#FFF5DA; border-color:#F0D68E; color:#7F5300; }
.la-mini.la-bad { background:#FDE6E2; border-color:#F3BDB4; color:#A3261A; }
.la-mini.la-none { background:#F4F6F5; border-color:#DCE3DF; color:#3E4A44; }
.la-yok { font-size:11.5px; color:#9AA8A0; white-space:nowrap; }
.la-etiket { display:inline-block; padding:4px 10px; border-radius:999px; font-size:11.5px; font-weight:700; white-space:nowrap; }
</style>
"""


# ================= GOOGLE SHEET =================
_SHEET_FN = None   # app.py'den verilir: Google Sheet'i (Spreadsheet nesnesi) döndüren fonksiyon

# Sağlık panelinin Sheet'indeki sayfa adları (sağlık panelinin kendi sayfalarıyla çakışmasın diye Limitli_ önekli)
SAYFA = {"Akakce": "Limitli_Akakce", "Gecmis": "Limitli_Gecmis", "Durum": "Limitli_Durum",
         "Limitli": "Limitli_Liste", "Eslestirme": "Limitli_Eslestirme",
         "Teklifler": "Limitli_Teklifler"}


def _sheet():
    return _SHEET_FN()


def _ws(ad, satir=1000, sutun=20):
    ad = SAYFA.get(ad, ad)
    sh = _sheet()
    try:
        return sh.worksheet(ad)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(ad, rows=satir, cols=sutun)


# Yerel deneme: secrets.toml'da yerel_test_klasoru verilirse Sheet yerine o klasördeki JSON dosyaları kullanılır
try:
    YEREL = str(st.secrets.get("yerel_test_klasoru", "") or "")
except Exception:
    YEREL = ""


@st.cache_data(ttl=300, show_spinner=False)
def oku(ad):
    if YEREL:
        import json, os
        yol = os.path.join(YEREL, ad + ".json")
        return json.load(open(yol, encoding="utf-8")) if os.path.exists(yol) else []
    try:
        return _sheet().worksheet(SAYFA.get(ad, ad)).get_all_values()
    except gspread.WorksheetNotFound:
        return []


def yaz(ad, satirlar):
    if YEREL:
        import json, os
        json.dump([[("" if v is None else v) for v in r] for r in satirlar],
                  open(os.path.join(YEREL, ad + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
        oku.clear()
        return
    ws = _ws(ad, max(len(satirlar) + 50, 200), max((len(satirlar[0]) if satirlar else 1) + 2, 10))
    ws.clear()
    if satirlar:
        ws.update(range_name="A1", values=satirlar, value_input_option="RAW")
    oku.clear()


def durum_oku():
    return {r[0]: r[1] for r in oku("Durum") if len(r) >= 2 and r[0]}


def durum_yaz(**alanlar):
    d = durum_oku()
    d.update({k: str(v) for k, v in alanlar.items()})
    yaz("Durum", [[k, v] for k, v in d.items()])


# ================= YARDIMCILAR =================
def sayi(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    t = str(v).strip().replace("₺", "").replace("TL", "").strip()
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def tl(v, kurus=True):
    if v is None:
        return "—"
    s = f"{v:,.2f}" if kurus else f"{v:,.0f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"


def yuzde(v):
    return ("+" if v > 0 else "") + f"{v:.1f}".replace(".", ",") + "%"


def ean_norm(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        return str(int(v))
    t = str(v).strip().lstrip("'")
    if re.fullmatch(r"\d+\.0", t):
        t = t[:-2]
    return t


def sade(x):
    x = str(x or "").lower().replace("ı", "i").replace("İ", "i")
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", x).strip()


def e(x):
    return html.escape(str(x or ""))


# ================= LİMİTLİ ADET LİSTESİ =================
def sutun_bul(basliklar, *anahtarlar, haric=()):
    """Anahtarlar öncelik sırasıyla denenir: önce tam eşleşme, sonra içeren."""
    for a in anahtarlar:
        for b in basliklar:
            if sade(b) == a:
                return b
    for a in anahtarlar:
        for b in basliklar:
            s = sade(b)
            if a in s and not any(h in s for h in haric):
                return b
    return None


def limitli_df():
    v = oku("Limitli")
    if len(v) < 2:
        return None, {}
    basliklar = [str(h).strip() or f"Sütun {i+1}" for i, h in enumerate(v[0])]
    df = pd.DataFrame([r + [""] * (len(basliklar) - len(r)) for r in v[1:]], columns=basliklar)
    kol = {
        "ean": sutun_bul(basliklar, "ean", "barkod", "gtin"),
        "ad": sutun_bul(basliklar, "isimlendirme", "urun adi", "urun ismi", "urun", "aciklama"),
        "kategori": sutun_bul(basliklar, "kategori", "alt grup", "grup"),
        "kod": sutun_bul(basliklar, "ozel kod", "urun kodu", "model", "sku"),
    }
    fiyatlar = [b for b in basliklar if any(a in sade(b) for a in ("fiyat", "kdv dahil", "birim"))
                and "kdv" != sade(b) and df[b].map(sayi).notna().mean() > 0.5]
    kol["fiyatlar"] = fiyatlar
    df = df[df[kol["ean"]].map(ean_norm) != ""] if kol["ean"] else df
    return df.reset_index(drop=True), kol


def varsayilan_ref(fiyatlar):
    for f in fiyatlar:
        s = sade(f)
        if "kdv dahil" in s and "liste" in s:
            return f
    for f in fiyatlar:
        if "kdv dahil" in sade(f):
            return f
    return fiyatlar[0] if fiyatlar else None


# ================= AKAKÇE =================
def akakce_df():
    v = oku("Akakce")
    if len(v) < 2:
        return pd.DataFrame(columns=["Akakçe Kod", "Akakçe Ürün Adı", "En Düşük Fiyat"])
    df = pd.DataFrame([r + [""] * (len(v[0]) - len(r)) for r in v[1:]], columns=v[0])
    df["Akakçe Kod"] = df["Akakçe Kod"].astype(str).str.strip()
    df["_fiyat"] = df["En Düşük Fiyat"].map(sayi)
    return df


def eslestirme():
    v = oku("Eslestirme")
    return {ean_norm(r[0]): str(r[1]).strip() for r in v[1:] if len(r) >= 2 and ean_norm(r[0]) and str(r[1]).strip()}


# Otomatik eşleştirme önerisi: isimlerdeki kelime ve model kodlarının (rakam içerenler) örtüşmesi
GENEL = {"oral", "b", "oral-b", "poc", "brush", "sarjli", "sarj", "edilebilir", "elektrikli", "dis", "fircasi", "firca",
         "fircas", "ve", "ile", "icin", "adet", "li", "lu", "lı", "set", "seti", "braun", "the", "pro"}


# İngilizce renk/ek adları -> Akakçe'deki Türkçe karşılıkları
CEVIRI = {"black": "siyah", "blk": "siyah", "bl": "siyah", "white": "beyaz", "wh": "beyaz", "gold": "gold", "gd": "gold",
          "rose": "pembe", "pink": "pembe", "quartz": "pembe", "blue": "mavi", "grey": "gri", "gray": "gri",
          "green": "yesil", "purple": "mor", "lavender": "mor", "red": "kirmizi", "silver": "gumus", "cosmic": "siyah",
          "kozmik": "siyah", "stardust": "beyaz", "duo": "2", "2ct": "2"}
RENKLER = {"siyah", "beyaz", "gold", "pembe", "mavi", "gri", "yesil", "mor", "kirmizi", "gumus"}


def jetonlar(x):
    s = sade(x).replace("-", " ").replace("/", " ")
    s = re.sub(r"(\d)\s*(li|lu|lü|lı|'li|'lu)\b", r"\1", s)
    s = re.sub(r"\b(io)\s*(\d+)", r"\1\2", s)        # "iO 10" ile "IO10" aynı olsun
    t = re.findall(r"[a-z0-9]+", s)
    return {CEVIRI.get(k, k) for k in t if k not in GENEL}


def benzerlik(a, b):
    ta, tb = jetonlar(a), jetonlar(b)
    if not ta or not tb:
        return 0.0
    ortak = ta & tb
    def agirlik(k):
        return 3.0 if re.search(r"\d", k) else 1.0
    pay = sum(agirlik(k) for k in ortak)
    payda = sum(agirlik(k) for k in ta | tb)
    # model kodu uyuşmazlığı (ör. IO9 vs IO10) cezası
    sayi_a = {k for k in ta if re.search(r"\d", k)}
    sayi_b = {k for k in tb if re.search(r"\d", k)}
    ceza = 0.6 if sayi_a and sayi_b and not (sayi_a & sayi_b) else 1.0
    renk_a, renk_b = ta & RENKLER, tb & RENKLER
    if renk_a and renk_b and not (renk_a & renk_b):
        ceza *= 0.3                                        # renk farklı: başka ürün
    return pay / payda * ceza


def oneri_bul(ad, kod, akakce):
    en, skor = None, 0.0
    for _, r in akakce.iterrows():
        s = max(benzerlik(f"{ad} {kod}", r["Akakçe Ürün Adı"]), benzerlik(ad, r["Akakçe Ürün Adı"]))
        if s > skor:
            en, skor = r["Akakçe Kod"], s
    return en, skor


# ================= KANALLAR (Akakçe ürün sayfasındaki teklifler) =================
# Pazaryerlerinde "resmi mağaza" sayılan satıcı adları (küçük harf, Türkçe karaktersiz aranır)
RESMI_SATICILAR = ["p&g turkiye", "p&g", "procter"]

# Her sütun: (başlık, [(alt etiket, platform anahtarı, tür)]). tür: "resmi" = P&G satıcısı,
# "kendi" = platformun kendi sattığı teklif (satıcı boş ya da platform adıyla aynı)
KANALLAR = [
    ("Trendyol", [("P&G", "trendyol", "resmi"), ("Trendyol", "trendyol", "kendi")]),
    ("Hepsiburada", [("P&G", "hepsiburada", "resmi"), ("Hepsiburada", "hepsiburada", "kendi")]),
    ("Amazon", [("P&G", "amazon", "resmi"), ("Amazon", "amazon", "kendi")]),
    ("Diğer pazaryeri P&G", [("P&G", "*", "resmi")]),
    ("Vatan", [("", "vatan", "kendi")]),
    ("MediaMarkt", [("", "mediamarkt", "kendi")]),
    ("Teknosa", [("", "teknosa", "kendi")]),
    ("Braunshop", [("", "braun", "kendi")]),
]
_ANA_PLATFORMLAR = {"trendyol", "hepsiburada", "amazon"}


def _resmi_mi(satici):
    s = sade(satici)
    return any(sade(r) in s for r in RESMI_SATICILAR) if s else False


def _kendi_mi(platform, satici, anahtar):
    p, s = sade(platform), sade(satici)
    if "pazaryeri" in p:                      # "MediaMarkt Pazaryeri" = MediaMarkt'taki başka satıcılar
        return False
    return not s or anahtar in s.replace(" ", "")


def teklifler_oku():
    """{akakce_kod: [{'platform','satici','fiyat','resmi'}]}"""
    v = oku("Teklifler")
    t = {}
    for r in v[1:]:
        if len(r) < 4 or not r[0]:
            continue
        f = sayi(r[3])
        if f:
            t.setdefault(str(r[0]).strip(), []).append(
                {"platform": r[1], "satici": r[2], "fiyat": f, "resmi": r[4] if len(r) > 4 else ""})
    return t


def kanal_fiyatlari(teklifler):
    """Bir ürünün teklif listesinden her kanal sütunu için [(etiket, fiyat, platform/satıcı)] üretir (en ucuz teklif)."""
    sonuc = {}
    for baslik, kalemler in KANALLAR:
        hucre = []
        for etiket, anahtar, tur in kalemler:
            adaylar = []
            for t in teklifler:
                p = sade(t["platform"]).replace(" ", "")
                if anahtar == "*":
                    if any(a in p for a in _ANA_PLATFORMLAR):
                        continue
                elif anahtar not in p:
                    continue
                if tur == "resmi" and _resmi_mi(t["satici"]):
                    adaylar.append(t)
                elif tur == "kendi" and not _resmi_mi(t["satici"]) and _kendi_mi(t["platform"], t["satici"], anahtar):
                    adaylar.append(t)
            if adaylar:
                en = min(adaylar, key=lambda x: x["fiyat"])
                yer = en["platform"] + (f" / {en['satici']}" if en["satici"] else "")
                hucre.append((etiket if anahtar != "*" else en["platform"], en["fiyat"], yer))
        sonuc[baslik] = hucre
    return sonuc


# ================= KARŞILAŞTIRMA =================
def karsilastir(df, kol, ref, akakce, esl, esik, teklifler=None):
    ak = {r["Akakçe Kod"]: r for _, r in akakce.iterrows()}
    teklifler = teklifler or {}
    satirlar = []
    for _, r in df.iterrows():
        ean = ean_norm(r[kol["ean"]])
        bizim = sayi(r[ref]) if ref else None
        kod = esl.get(ean, "")
        a = ak.get(kod) if kod else None
        af = a["_fiyat"] if a is not None else None
        if not kod:
            durum, fark = "eslesmedi", None
        elif a is None or af is None:
            durum, fark = "fiyatyok", None
        elif not bizim:
            durum, fark = "fiyatyok", None
        else:
            fark = (af - bizim) / bizim * 100
            durum = "bad" if fark < 0 else ("warn" if fark < esik else "ok")
        satirlar.append({
            "ean": ean, "ad": r[kol["ad"]] if kol["ad"] else ean,
            "kategori": str(r[kol["kategori"]]).strip() if kol["kategori"] else "",
            "kod": str(r[kol["kod"]]).strip() if kol["kod"] else "",
            "bizim": bizim, "diger": {f: sayi(r[f]) for f in kol["fiyatlar"]
                                      if f != ref and ("kdv dahil" in sade(f)) == ("kdv dahil" in sade(ref))},
            "akakce_kod": kod, "akakce": af,
            "akakce_ad": a.get("Akakçe Ürün Adı", "") if a is not None else "",
            "link": a.get("Link", "") if a is not None else "",
            "gorsel": a.get("Görsel", "") if a is not None else "",
            "satici": a.get("Satıcı", "") if a is not None else "",
            "satici_logo": a.get("Satıcı Logo", "") if a is not None else "",
            "satici_sayisi": a.get("Satıcı Sayısı", "") if a is not None else "",
            "fark": fark, "durum": durum,
            "kanallar": kanal_fiyatlari(teklifler.get(kod, [])) if kod else {},
            "teklif_var": bool(kod and teklifler.get(kod)),
            "en_ucuz_yer": "",
        })
        tk = teklifler.get(kod, []) if kod else []
        if tk:
            en = min(tk, key=lambda x: x["fiyat"])
            satirlar[-1]["en_ucuz_yer"] = en["platform"] + (f" / {en['satici']}" if en["satici"] else "")
    return satirlar


def renk_durumu(fiyat, bizim, esik):
    if fiyat is None or not bizim:
        return "none", None
    f = (fiyat - bizim) / bizim * 100
    return ("bad" if f < 0 else ("warn" if f < esik else "ok")), f


DURUM_ADI = {"bad": "Akakçe bizden ucuz", "warn": "Marj dar", "ok": "Uygun",
             "fiyatyok": "Akakçe fiyatı yok", "eslesmedi": "Eşleştirilmedi"}


def _mini(etiket, fiyat, bizim, esik, ipucu=""):
    d, f = renk_durumu(fiyat, bizim, esik)
    ust = f"<span class='la-me'>{e(etiket)}</span>" if etiket else ""
    alt = f"<span class='la-d'>{yuzde(f)}</span>" if f is not None else ""
    return (f"<span class='la-mini la-{d}' title='{e(ipucu)}'>{ust}<span class='la-p'>{tl(fiyat, kurus=False)}</span>"
            f"{alt}</span>")


def tablo_html(satirlar, ref, esik):
    kanal_bas = "".join(f"<th>{e(k)}</th>" for k, _ in KANALLAR)
    bas = (f"<tr><th class='la-sol'>Ürün</th><th>Limitli Adet<span class='la-alt'>{e(ref)}</span></th>"
           f"<th>Akakçe En Düşük</th>{kanal_bas}</tr>")
    g = []
    for s in satirlar:
        img = f"<img src='{e(s['gorsel'])}' loading='lazy'>" if s["gorsel"] else "<span class='la-bos'></span>"
        alt = " · ".join(x for x in [s["kod"], s["ean"]] if x)
        urun = f"<div class='la-urun'>{img}<div><b>{e(s['ad'])}</b><small>{e(alt)}</small></div></div>"
        diger = "".join(f"<span class='la-alt'>{e(k)}: {tl(v)}</span>" for k, v in s["diger"].items() if v)
        bizim = f"<span class='la-fiyat'>{tl(s['bizim'])}</span>{diger}"
        d = s["durum"]
        if d in ("ok", "warn", "bad"):
            yer = s["en_ucuz_yer"] or s["satici"]
            ic = (f"<span class='la-hucre la-{d}'><span class='la-p'>{tl(s['akakce'])}</span>"
                  f"<span class='la-d'>{yuzde(s['fark'])}</span></span>"
                  + (f"<span class='la-alt'>{e(yer)}</span>" if yer else ""))
        elif d == "fiyatyok":
            ic = "<span class='la-hucre la-none'><span class='la-p'>Fiyat yok</span></span>"
        else:
            ic = "<span class='la-hucre la-none'><span class='la-p'>Eşleştirilmedi</span></span>"
        if s["link"]:
            ic = f"<a class='la-lnk' href='{e(s['link'])}' target='_blank' title='{e(s['akakce_ad'])}'>{ic}</a>"
        kanallar = []
        for k, _ in KANALLAR:
            hucre = s["kanallar"].get(k, [])
            if hucre:
                icerik = "".join(_mini(et, f, s["bizim"], esik, yer) for et, f, yer in hucre)
                if s["link"]:
                    icerik = f"<a class='la-lnk' href='{e(s['link'])}' target='_blank'>{icerik}</a>"
            elif s["teklif_var"]:
                icerik = "<span class='la-yok'>Satışta yok</span>"
            else:
                icerik = "<span class='la-yok'>—</span>"
            kanallar.append(f"<td>{icerik}</td>")
        g.append(f"<tr><td class='la-sol'>{urun}</td><td>{bizim}</td><td>{ic}</td>{''.join(kanallar)}</tr>")
    return f"<div class='la-kart'><table class='la-t'>{bas}{''.join(g)}</table></div>"


def excel_cikti(satirlar, ref):
    tablo = pd.DataFrame([{
        "EAN": s["ean"], "Ürün": s["ad"], "Kod": s["kod"], "Kategori": s["kategori"],
        f"Limitli Adet ({ref})": s["bizim"], **{k: v for k, v in s["diger"].items()},
        "Akakçe En Düşük": s["akakce"], "Fark %": round(s["fark"], 1) if s["fark"] is not None else None,
        "Durum": DURUM_ADI[s["durum"]], "En Ucuz Satıcı": s["satici"], "Satıcı Sayısı": s["satici_sayisi"],
        "Akakçe Ürün": s["akakce_ad"], "Akakçe Link": s["link"],
        **{(f"{k} {et}".strip() if et else k): f for k, _ in KANALLAR for et, f, _y in s["kanallar"].get(k, [])
           if k != "Diğer pazaryeri P&G"},
        "Diğer pazaryeri P&G": " | ".join(f"{et}: {f:,.0f}".replace(",", ".")
                                          for et, f, _y in s["kanallar"].get("Diğer pazaryeri P&G", [])),
    } for s in satirlar])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        tablo.to_excel(w, index=False, sheet_name="Karşılaştırma")
        ws = w.sheets["Karşılaştırma"]
        for i, c in enumerate(tablo.columns, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, min(45, len(str(c)) + 4))
    return buf.getvalue()


def tarama_yasi_saat(metin):
    try:
        t = datetime.strptime(metin, "%d.%m.%Y %H:%M").replace(tzinfo=TR)
        return (datetime.now(TR) - t).total_seconds() / 3600
    except Exception:
        return None


# ================= SAYFALAR =================
def ust_bant(durum):
    ay = durum.get("limitli_ay", "")
    c1, c2 = st.columns([5, 1])
    c1.markdown(f"<div class='la-baslik'><b>Limitli Adet · Akakçe Fiyat Kontrolü</b>"
                f"<span>B2B eczane / geleneksel bayi fiyatlarımız ile Akakçe'deki en düşük piyasa fiyatı</span>"
                f"<i class='la-ay'>Liste: {e(ay) or 'yüklenmedi'}</i></div>", unsafe_allow_html=True)
    if c2.button("↻ Yenile", key="la_yenile", use_container_width=True):
        oku.clear()
        st.rerun()
    if durum.get("son_hata") and durum.get("son_deneme") != durum.get("son_tarama"):
        st.warning(f"Son Akakçe taraması ({durum.get('son_deneme')}) hata verdi: {durum.get('son_hata')}")


def karsilastirma_sayfasi():
    df, kol = limitli_df()
    if df is None:
        st.info("Henüz Limitli Adet listesi yüklenmedi. **Liste Yükle** sekmesinden aylık Excel'i yükleyin.")
        return
    if not kol["fiyatlar"]:
        st.error("Yüklenen listede fiyat sütunu bulunamadı.")
        return
    akakce = akakce_df()
    esl = eslestirme()

    c1, c2, c3, c4 = st.columns([2.2, 1.6, 1.6, 1.2])
    fiyatlar = kol["fiyatlar"]
    vars_ref = varsayilan_ref(fiyatlar)
    ref = c1.selectbox("Karşılaştırılacak Limitli Adet fiyatı", fiyatlar, index=fiyatlar.index(vars_ref))
    kategoriler = sorted({str(x).strip() for x in df[kol["kategori"]]} - {""}) if kol["kategori"] else []
    kat = c2.multiselect("Kategori", kategoriler, placeholder="Tümü")
    durum_sec = c3.multiselect("Durum", list(DURUM_ADI.values()), placeholder="Tümü")
    esik = c4.number_input("Marj dar eşiği (%)", 0, 100, VARSAYILAN_ESIK, 1,
                           help="Akakçe fiyatı bizim fiyatın bu yüzdeden daha az üstündeyse 'Marj dar' (sarı) sayılır.")

    teklifler = teklifler_oku()
    satirlar = karsilastir(df, kol, ref, akakce, esl, esik, teklifler)
    n = len(satirlar)
    say = {k: sum(1 for s in satirlar if s["durum"] == k) for k in DURUM_ADI}
    st.markdown(f"""<div class='la-kpis'>
      <div class='la-kpi'><div class='la-l'>Ürün</div><div class='la-v'>{n}</div><div class='la-s'>Limitli Adet listesinde</div></div>
      <div class='la-kpi la-bad'><div class='la-l'>Akakçe bizden ucuz</div><div class='la-v'>{say['bad']}</div><div class='la-s'>Akakçe en düşük &lt; bizim fiyat</div></div>
      <div class='la-kpi la-warn'><div class='la-l'>Marj dar</div><div class='la-v'>{say['warn']}</div><div class='la-s'>Akakçe bizden en fazla %{esik} yukarıda</div></div>
      <div class='la-kpi la-ok'><div class='la-l'>Uygun</div><div class='la-v'>{say['ok']}</div><div class='la-s'>Akakçe bizden %{esik}+ yukarıda</div></div>
      <div class='la-kpi'><div class='la-l'>Kontrol edilemeyen</div><div class='la-v'>{say['eslesmedi'] + say['fiyatyok']}</div><div class='la-s'>{say['eslesmedi']} eşleşmemiş · {say['fiyatyok']} fiyatsız</div></div>
    </div>""", unsafe_allow_html=True)

    goster = [s for s in satirlar if (not kat or s["kategori"] in kat)
              and (not durum_sec or DURUM_ADI[s["durum"]] in durum_sec)]
    sira = st.radio("Sıralama", ["Listedeki sıra", "Fark (en kötü önce)", "Fark (en iyi önce)"], horizontal=True,
                    label_visibility="collapsed")
    if sira != "Listedeki sıra":
        ters = sira.endswith("iyi önce)")
        goster = sorted(goster, key=lambda s: (s["fark"] is None, (-s["fark"] if ters else s["fark"])
                                               if s["fark"] is not None else 0))
    st.markdown(tablo_html(goster, ref, esik), unsafe_allow_html=True)
    st.download_button("Excel olarak indir", excel_cikti(goster, ref),
                       file_name=f"Limitli_Adet_vs_Akakce_{datetime.now(TR):%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("Kanal sütunları Akakçe ürün sayfasındaki tekliflerden gelir. P&G = pazaryerindeki P&G Türkiye mağazası; "
               "Trendyol / Hepsiburada / Amazon = platformun kendi sattığı teklif; Vatan, MediaMarkt, Teknosa = kendi "
               "sitesi; Braunshop = Braun resmi sitesi. Renkler Limitli Adet fiyatına göredir. Hücrenin üzerine gelince "
               "satıcı görünür, tıklayınca Akakçe sayfası açılır.")
    if say["eslesmedi"]:
        st.caption(f"{say['eslesmedi']} ürün Akakçe ile eşleştirilmemiş. **Eşleştirme** sekmesinden eşleştirebilirsiniz.")
    if teklifler:
        with st.expander("Akakçe tekliflerinde görülen platform / satıcılar"):
            sayac = {}
            for liste in teklifler.values():
                for t in liste:
                    k = (t["platform"], t["satici"] or "(kendisi)")
                    sayac[k] = sayac.get(k, 0) + 1
            st.dataframe(pd.DataFrame([{"Platform": p, "Satıcı": sa, "Ürün sayısı": n}
                                       for (p, sa), n in sorted(sayac.items())]),
                         hide_index=True, use_container_width=True, height=320)


def _hucre_degeri(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (int, float)):
        return float(v) if isinstance(v, float) else int(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%d.%m.%Y")
    return str(v).strip()


def yukleme_sayfasi():
    durum = durum_oku()
    st.markdown("#### Aylık Limitli Adet listesini yükle")
    st.caption("Excel'de EAN (barkod), ürün adı ve en az bir fiyat sütunu olmalı (örn. *Kdv Dahil Fiyat Liste Fiyatı*). "
               "Yeni yükleme bir önceki listenin yerine geçer; Akakçe eşleştirmeleri EAN'a bağlı olduğu için korunur.")
    if durum.get("limitli_ay"):
        st.info(f"Şu anki liste: **{durum.get('limitli_ay')}** · {durum.get('limitli_dosya', '')} · "
                f"yüklenme {durum.get('limitli_yukleme', '')}")
    dosya = st.file_uploader("Excel dosyası", type=["xlsx", "xlsm"])
    if not dosya:
        return
    try:
        xl = pd.ExcelFile(dosya)
        sayfa = st.selectbox("Sayfa", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
        ham = pd.read_excel(xl, sheet_name=sayfa, header=None, dtype=object)
    except Exception as ex:
        st.error(f"Dosya okunamadı: {ex}")
        return
    # Başlık satırını bul (EAN / Barkod yazan ilk satır)
    bas_i = 0
    for i in range(min(15, len(ham))):
        if any(sade(x) in ("ean", "barkod", "gtin", "ean kodu") for x in ham.iloc[i].tolist()):
            bas_i = i
            break
    basliklar = [str(x).strip() if pd.notna(x) else "" for x in ham.iloc[bas_i].tolist()]
    dolu = [i for i, b in enumerate(basliklar) if b]
    veri = ham.iloc[bas_i + 1:, dolu]
    veri.columns = [basliklar[i] for i in dolu]
    veri = veri.dropna(how="all")
    ean_k = sutun_bul(list(veri.columns), "ean", "barkod", "gtin")
    if not ean_k:
        st.error("EAN / Barkod sütunu bulunamadı.")
        return
    veri = veri[veri[ean_k].map(ean_norm) != ""]
    veri[ean_k] = veri[ean_k].map(ean_norm)
    st.write(f"**{len(veri)} ürün**, sütunlar: {', '.join(veri.columns)}")
    st.dataframe(veri.head(15), hide_index=True, use_container_width=True)
    ay_m = re.search(r"(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)",
                     dosya.name, re.I)
    ay_vars = (ay_m.group(1).capitalize() + f" {datetime.now(TR).year}") if ay_m else datetime.now(TR).strftime("%m.%Y")
    ay = st.text_input("Bu liste hangi ay için?", ay_vars)
    if st.button("Listeyi kaydet", type="primary"):
        satirlar = [list(veri.columns)] + [[_hucre_degeri(v) for v in r] for r in veri.itertuples(index=False)]
        with st.spinner("Kaydediliyor..."):
            yaz("Limitli", satirlar)
            durum_yaz(limitli_ay=ay, limitli_dosya=dosya.name,
                      limitli_yukleme=datetime.now(TR).strftime("%d.%m.%Y %H:%M"))
        st.success(f"{len(veri)} ürünlük liste kaydedildi ({ay}).")
        esl = eslestirme()
        yeni = sum(1 for x in veri[ean_k] if x not in esl)
        if yeni:
            st.warning(f"{yeni} ürünün Akakçe eşleştirmesi yok. Bu ürünleri Akakçe'deki 'Limitli Adet' listesine ekleyip "
                       f"tarama sonrası **Eşleştirme** sekmesinden eşleştirin.")


def eslestirme_sayfasi():
    df, kol = limitli_df()
    akakce = akakce_df()
    if df is None:
        st.info("Önce Limitli Adet listesini yükleyin.")
        return
    if akakce.empty:
        st.info("Henüz Akakçe taraması yok. Ürünleri Akakçe'deki 'Limitli Adet' listesine ekleyip taramayı çalıştırın.")
        return
    esl = eslestirme()
    secenek = {r["Akakçe Kod"]: f"{r['Akakçe Ürün Adı']} · {tl(r['_fiyat'])} · {r['Akakçe Kod']}"
               for _, r in akakce.iterrows()}
    etiket_kod = {v: k for k, v in secenek.items()}
    st.markdown("#### Limitli Adet ürünü ↔ Akakçe ürünü")
    st.caption("Her EAN için Akakçe listesindeki doğru ürünü seçin. Boş olanlara sistem isim benzerliğine göre öneri getirir "
               "(**Öneri** sütunu). Kontrol edip **Kaydet**'e basın. Eşleştirme EAN'a bağlıdır, sonraki aylarda tekrar gerekmez.")

    kullanilan = set(esl.values())
    satir = []
    for _, r in df.iterrows():
        ean = ean_norm(r[kol["ean"]])
        ad = r[kol["ad"]] if kol["ad"] else ean
        kod = str(r[kol["kod"]]).strip() if kol["kod"] else ""
        mevcut = esl.get(ean, "")
        oneri = ""
        if not mevcut:
            ok_, skor = oneri_bul(ad, kod, akakce)
            if ok_ and skor >= 0.5:
                oneri = f"%{skor*100:.0f}"
                mevcut = ok_
        satir.append({"EAN": ean, "Ürün": ad, "Akakçe ürünü": secenek.get(mevcut, ""), "Öneri": oneri})
    tablo = pd.DataFrame(satir)
    yalniz_bos = st.toggle("Sadece kaydedilmemiş eşleştirmeleri göster", value=False)
    if yalniz_bos:
        tablo = tablo[tablo["EAN"].map(lambda x: x not in esl)]
    duz = st.data_editor(
        tablo, hide_index=True, use_container_width=True, height=min(38 * (len(tablo) + 1) + 4, 720),
        disabled=["EAN", "Ürün", "Öneri"],
        column_config={
            "Akakçe ürünü": st.column_config.SelectboxColumn("Akakçe ürünü", options=[""] + list(secenek.values()),
                                                             width="large"),
            "Öneri": st.column_config.TextColumn("Öneri", help="Kaydedilmemiş, sistemin önerdiği eşleşme ve benzerlik puanı"),
        }, key="esl_editor")
    c1, c2 = st.columns([1, 4])
    if c1.button("Kaydet", type="primary"):
        yeni = dict(esl)
        for _, r in duz.iterrows():
            k = etiket_kod.get(r["Akakçe ürünü"], "")
            if k:
                yeni[r["EAN"]] = k
            else:
                yeni.pop(r["EAN"], None)
        yaz("Eslestirme", [["EAN", "Akakçe Kod"]] + [[k, v] for k, v in yeni.items()])
        st.success(f"{len(yeni)} eşleştirme kaydedildi.")
        st.rerun()
    cift = pd.Series([etiket_kod.get(x, "") for x in duz["Akakçe ürünü"]])
    cift = cift[cift != ""]
    if cift.duplicated().any():
        c2.warning("Aynı Akakçe ürünü birden fazla EAN'a seçilmiş, kontrol edin (renk varyantları aynı Akakçe ürünü olabilir).")
    bos_ak = [secenek[k] for k in secenek if k not in set(cift) | kullanilan]
    if bos_ak:
        with st.expander(f"Akakçe listesinde olup hiçbir EAN'a bağlanmamış {len(bos_ak)} ürün"):
            for x in bos_ak:
                st.write("• " + x)


def gecmis_sayfasi():
    v = oku("Gecmis")
    df, kol = limitli_df()
    if len(v) < 2 or df is None:
        st.info("Geçmiş, tarama her gün çalıştıkça birikir.")
        return
    g = pd.DataFrame(v[1:], columns=v[0][:len(v[1])] if v[1:] else v[0])
    g["Tarih"] = pd.to_datetime(g["Tarih"], errors="coerce")
    g["Fiyat"] = g["En Düşük Fiyat"].map(sayi)
    esl = eslestirme()
    urunler = {f"{r[kol['ad']]} · {ean_norm(r[kol['ean']])}": ean_norm(r[kol["ean"]]) for _, r in df.iterrows()
               if ean_norm(r[kol["ean"]]) in esl}
    if not urunler:
        st.info("Geçmiş görmek için önce ürünleri eşleştirin.")
        return
    sec = st.selectbox("Ürün", list(urunler))
    ean = urunler[sec]
    seri = g[g["Akakçe Kod"].astype(str) == esl[ean]].dropna(subset=["Tarih", "Fiyat"]).sort_values("Tarih")
    ref = varsayilan_ref(kol["fiyatlar"])
    bizim = sayi(df[df[kol["ean"]].map(ean_norm) == ean].iloc[0][ref]) if ref else None
    if seri.empty:
        st.info("Bu ürün için henüz geçmiş kaydı yok.")
        return
    cizim = pd.DataFrame({"Akakçe en düşük": seri["Fiyat"].values}, index=seri["Tarih"].values)
    if bizim:
        cizim[f"Limitli Adet ({ref})"] = bizim
    st.line_chart(cizim, height=360)
    st.caption(f"Son {len(seri)} gün · en düşük {tl(seri['Fiyat'].min())} · en yüksek {tl(seri['Fiyat'].max())}")


# ================= SEKME =================
def son_tarama(sheet_fn):
    """Sağlık panelinin üst kartı için: (tarih metni, güncel mi, etiket)."""
    global _SHEET_FN
    _SHEET_FN = sheet_fn
    try:
        son = durum_oku().get("son_tarama", "")
    except Exception:
        son = ""
    yas = tarama_yasi_saat(son) if son else None
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})", son)
    return (f"{m.group(1)} · {m.group(2)}" if m else ""), (yas is not None and yas <= GECIKME_SAAT), "Son Akakçe taraması"


def sayfa(sheet_fn):
    """Sağlık panelindeki 'Limitli Adet' sekmesi. sheet_fn: Spreadsheet döndüren fonksiyon."""
    global _SHEET_FN
    _SHEET_FN = sheet_fn
    st.markdown(_CSS, unsafe_allow_html=True)
    try:
        durum = durum_oku()
    except Exception as ex:
        st.error(f"Google Sheet okunamadı: {ex}")
        return
    ust_bant(durum)
    s1, s2, s3, s4 = st.tabs(["Karşılaştırma", "Liste Yükle", "Eşleştirme", "Fiyat Geçmişi"])
    with s1:
        karsilastirma_sayfasi()
    with s2:
        yukleme_sayfasi()
    with s3:
        eslestirme_sayfasi()
    with s4:
        gecmis_sayfasi()
