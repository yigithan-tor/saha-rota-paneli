"""
Saha Rota Paneli — Streamlit uygulamasi
python -m streamlit run app.py
"""
import sqlite3
import pandas as pd
import streamlit as st
import folium
from folium.plugins import PolyLineTextPath
import streamlit.components.v1 as components

def harita_goster(m, height, key):
    """Haritayi statik HTML olarak gomer — st_folium'un aksine fare
    hareketinde Python'a geri donmez, bu yuzden cok daha akici."""
    components.html(m.get_root().render(), height=height)

st.set_page_config(page_title="Saha Rota Paneli", layout="wide")
st.markdown("""
<style>
  .block-container { padding-top: 2rem; padding-bottom: 1rem;
                     padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
</style>
""", unsafe_allow_html=True)

# ── Veri ──────────────────────────────────────────────────────
@st.cache_data
def veriyi_yukle():
    con = sqlite3.connect("routes.db")
    df = pd.read_sql("SELECT * FROM routes", con)
    con.close()
    return df

df = veriyi_yukle()

# ── (Not 3) Her personel icin SABIT renk ──────────────────────
PERSONEL_RENK = {
    "Berkcan": "#3b7dd8",   # mavi
    "Onur":    "#e07b39",   # turuncu
}
YEDEK_PALET = ["#3cb44b", "#911eb4", "#e6194b", "#008080", "#f032e6"]
def personel_renk(p):
    if p in PERSONEL_RENK:
        return PERSONEL_RENK[p]
    idx = sorted(df.employee.unique()).index(p)
    return YEDEK_PALET[idx % len(YEDEK_PALET)]

# (Not 1) home/otel dugumleri icin tek, notr renk
DUGUM_RENK = "#3a3a3a"   # koyu gri — tum ev/otel noktalari ayni

def gun_etiketi(day_type):
    if not isinstance(day_type, str): return ""
    if "Start"     in day_type: return "trip · başlangıç"
    if "Continues" in day_type: return "trip · devam"
    if "End"       in day_type: return "trip · son"
    return ""

# ── Numarali / harfli isaret ikonu (Not 4) ────────────────────
def daire_ikon(metin, arka_renk, cap=18, yazi=10):
    return folium.DivIcon(
        icon_size=(cap, cap), icon_anchor=(cap // 2, cap // 2),
        html=(f'<div style="background:{arka_renk};width:{cap}px;height:{cap}px;'
              f'border-radius:50%;border:2px solid white;'
              f'box-shadow:0 0 3px rgba(0,0,0,.55);color:white;'
              f'font-size:{yazi}px;font-weight:700;'
              f'display:flex;align-items:center;justify-content:center;'
              f'box-sizing:border-box;'
              f'font-family:sans-serif">{metin}</div>'))

def dugum_etiketi(satir):
    """Ev -> P, Otel -> otel kodu (H001 gibi)."""
    if satir.location == "Home":
        return "P"
    if satir.location == "Hotel":
        return satir.hotel if pd.notna(satir.hotel) else "H"
    return "?"

# ── Bir gunun rotasini haritaya cizer ────────────────────────
def rota_ciz(harita, gun_df, cizgi_renk, tooltip_on=""):
    hd = gun_df.dropna(subset=["latitude", "longitude"]).sort_values("stop_no")
    if len(hd) == 0:
        return

    # Ince cizgi + uzerinde kucuk yon oklari
    koord = list(zip(hd.latitude, hd.longitude))
    pl = folium.PolyLine(koord, color=cizgi_renk, weight=2,
                         opacity=0.85, tooltip=tooltip_on)
    pl.add_to(harita)
    PolyLineTextPath(
        pl, "          \u25B6          ", repeat=True, center=False, offset=3,
        attributes={"fill": cizgi_renk, "font-size": "7"},
    ).add_to(harita)

    # Ziyaretin gun numarasi (ay icindeki gun) — "2026-06-06" -> 6
    gun_no = int(str(hd.date.iloc[0]).split("-")[2])

    # Isaretler
    for _, s in hd.iterrows():
        if s.stop_type == "Farm Visit":
            # (Not 4) Sayi = ziyaretin gerceklestigi gun (ay icindeki)
            folium.Marker(
                [s.latitude, s.longitude],
                icon=daire_ikon(gun_no, cizgi_renk),
                tooltip=f"{tooltip_on}{s.stop_no}. {s.location} ({s.arrival})",
            ).add_to(harita)
        else:
            # (Not 1 + 4) Ev/otel: tek renk, P veya otel kodu
            etiket = dugum_etiketi(s)
            folium.Marker(
                [s.latitude, s.longitude],
                icon=daire_ikon(etiket, DUGUM_RENK, cap=20, yazi=9),
                tooltip=f"{tooltip_on}{etiket} — {s.location} ({s.arrival})",
            ).add_to(harita)

@st.cache_data
def hafta_haritasi():
    """Her tarihi kullanici-dostu hafta etiketine esler."""
    tarihler = pd.to_datetime(sorted(df.date.unique()))
    iso = tarihler.isocalendar()
    # ISO hafta -> sirali "Hafta N" etiketi + tarih araligi
    haftalar = {}
    sirali_iso = sorted(set(iso.week))
    for n, wk in enumerate(sirali_iso, start=1):
        gunler = [t for t, w in zip(tarihler, iso.week) if w == wk]
        bas = min(gunler); bit = max(gunler)
        haftalar[wk] = f"Hafta {n} ({bas.strftime('%d')}–{bit.strftime('%d')} Haz)"
    return {t.strftime("%Y-%m-%d"): haftalar[w]
            for t, w in zip(tarihler, iso.week)}

HAFTA = hafta_haritasi()

@st.cache_data
def gun_ozeti():
    rows = []
    for _, g in df[["employee","date"]].drop_duplicates().iterrows():
        gd = df[(df.employee==g.employee)&(df.date==g.date)].sort_values("stop_no")
        rows.append({
            "employee": g.employee, "date": g.date,
            "hafta": HAFTA[g.date],
            "tag":   gun_etiketi(gd.day_type.iloc[0]),
            "farms": int((gd.stop_type=="Farm Visit").sum()),
            "start": gd.arrival.iloc[0], "end": gd.arrival.iloc[-1],
        })
    return pd.DataFrame(rows)

OZET = gun_ozeti()

# ── Session state ─────────────────────────────────────────────
for personel in df.employee.unique():
    for g in df[df.employee==personel].date.unique():
        k = f"cb_{personel}_{g}"
        if k not in st.session_state:
            st.session_state[k] = True

def toggle_all(personel):
    # Sadece o an secili haftalardaki gunleri toggle et
    secili_haftalar = st.session_state.get("hafta_filtre", None)
    p_gunler = sorted(df[df.employee==personel].date.unique())
    if secili_haftalar:
        p_gunler = [g for g in p_gunler if HAFTA.get(g) in secili_haftalar]
    hepsi = all(st.session_state.get(f"cb_{personel}_{g}", True) for g in p_gunler)
    for g in p_gunler:
        st.session_state[f"cb_{personel}_{g}"] = not hepsi

# ── Kucuk aciklama (harita lejandi) ───────────────────────────
def lejand():
    st.markdown(
        "<div style='font-size:12px;color:#555;line-height:1.6'>"
        "<b>Gösterim:</b> çizgi + küçük oklar = rota ve gidiş yönü &nbsp;|&nbsp; "
        "sayılı daire = ziyaretin günü (ay içinde) &nbsp;|&nbsp; "
        "<span style='background:#3a3a3a;color:white;padding:0 5px;border-radius:8px'>P</span> "
        "personel evi &nbsp;|&nbsp; "
        "<span style='background:#3a3a3a;color:white;padding:0 5px;border-radius:8px'>H…</span> "
        "otel</div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
st.title("Saha Rota Paneli")
sekme1, sekme2, sekme3 = st.tabs(
    ["📅 Günlük Program", "🗺️ Genel Harita", "📋 Tüm Tablo"])

# ═══════════════════════════════════════════════════════════════
# SEKME 1 — GÜNLÜK PROGRAM
# ═══════════════════════════════════════════════════════════════
with sekme1:
    st.caption("Saha personeli için: bir çalışanın bir gününü tablo + harita olarak gösterir.")
    f1, f2 = st.columns(2)
    with f1:
        calisan = st.selectbox("Çalışan", sorted(df.employee.unique()), key="g_cal")
    with f2:
        gunler = sorted(df[df.employee==calisan].date.unique())
        gun    = st.selectbox("Gün", gunler, key="g_gun")

    gd = df[(df.employee==calisan)&(df.date==gun)].sort_values("stop_no")
    farm = (gd.stop_type=="Farm Visit").sum()
    otel = gd.hotel.iloc[0] if len(gd) and pd.notna(gd.hotel.iloc[0]) else "-"

    # Verimlilik: saha suresi / toplam gun suresi (%)
    saha_dk  = gd["time_on_site"].fillna(0).sum()
    yolcu_dk = gd["travel_min"].fillna(0).sum()
    toplam_dk = saha_dk + yolcu_dk
    verimlilik = f"%{int(round(saha_dk / toplam_dk * 100))}" if toplam_dk > 0 else "-"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Çiftlik ziyareti", int(farm))
    k2.metric("Gün başlangıcı",   gd.arrival.iloc[0] if len(gd) else "-")
    k3.metric("Gün bitişi",       gd.arrival.iloc[-1] if len(gd) else "-")
    with k4:
        st.metric("Operasyon verimliliği", verimlilik)
        st.markdown(
            f"<span style='color:#aaa;font-size:11px'>"
            f"{int(saha_dk)} dk saha / {int(toplam_dk)} dk toplam</span>",
            unsafe_allow_html=True)
    k5.metric("Konaklama", otel)

    detay = st.checkbox("Tüm detay sütunlarını göster", value=False, key="g_detay")
    st.divider()

    sol, sag = st.columns([1,1])
    with sol:
        st.subheader("Gün programı")
        if detay:
            st.dataframe(gd, use_container_width=True, hide_index=True)
        else:
            sade = gd[["stop_no","location","task","arrival",
                        "departure","time_on_site","break_taken"]].rename(columns={
                "stop_no":"Sıra","location":"Konum","task":"Görev",
                "arrival":"Varış","departure":"Ayrılış",
                "time_on_site":"Süre (dk)","break_taken":"Mola"})
            st.dataframe(sade, use_container_width=True, hide_index=True)

    with sag:
        st.subheader("Harita")
        hd = gd.dropna(subset=["latitude","longitude"])
        if len(hd)==0:
            st.info("Bu gün için koordinat bulunamadı.")
        else:
            m = folium.Map(location=[hd.latitude.mean(), hd.longitude.mean()], zoom_start=9)
            rota_ciz(m, gd, personel_renk(calisan))
            harita_goster(m, height=430, key="g_map")
            lejand()

# ═══════════════════════════════════════════════════════════════
# SEKME 2 — GENEL HARİTA
# ═══════════════════════════════════════════════════════════════
with sekme2:
    st.caption("Yönetim ve test için: günleri seçip haritada üst üste görüntüleyin.")

    # Hafta filtresi (ust kisim)
    tum_haftalar = sorted(set(OZET.hafta),
                          key=lambda h: int(h.split()[1]))  # "Hafta N" -> N
    secili_haftalar = st.multiselect(
        "Hafta filtresi", tum_haftalar, default=tum_haftalar,
        key="hafta_filtre",
        help="Sadece seçili haftaların günleri panelde ve haritada görünür.")

    # Panel daraltildi (1:6), harita buyudu
    sidebar, harita_alan = st.columns([1, 6])
    secili = []

    with sidebar:
        for personel in sorted(df.employee.unique()):
            # Sadece secili haftalardaki gunler
            p_ozet = OZET[(OZET.employee==personel) &
                          (OZET.hafta.isin(secili_haftalar))].sort_values("date")
            p_renk = personel_renk(personel)

            bh1, bh2 = st.columns([2, 1])
            with bh1:
                st.markdown(
                    f"<span style='background:{p_renk};width:11px;height:11px;"
                    f"border-radius:3px;display:inline-block;margin-right:5px'></span>"
                    f"**{personel}** "
                    f"<span style='color:#8a877d;font-size:12px'>({len(p_ozet)} gün)</span>",
                    unsafe_allow_html=True)
            with bh2:
                st.button("tümü", key=f"tog_{personel}",
                          on_click=toggle_all, args=(personel,),
                          use_container_width=True)

            with st.container(border=True):
                if len(p_ozet) == 0:
                    st.markdown("<span style='color:#aaa;font-size:11px'>"
                                "(seçili haftada gün yok)</span>",
                                unsafe_allow_html=True)
                for _, oz in p_ozet.iterrows():
                    anahtar = f"cb_{personel}_{oz.date}"
                    cb_col, bilgi_col = st.columns([0.15, 0.85])
                    with cb_col:
                        st.checkbox("", key=anahtar, label_visibility="collapsed")
                    with bilgi_col:
                        st.markdown(
                            f"<div style='padding:3px 0;font-size:12px;line-height:1.35'>"
                            f"<span style='font-weight:500'>{oz.date}</span>"
                            + (f" <span style='color:#b8860b;font-size:9.5px'>"
                               f"({oz.tag})</span>" if oz.tag else "")
                            + f"<br><span style='color:#8a877d;font-size:10.5px'>"
                            f"{oz.farms} durak · {oz.start}–{oz.end}"
                            f"</span></div>", unsafe_allow_html=True)
                    if st.session_state.get(anahtar, True):
                        secili.append((personel, oz.date))
            st.markdown("<br>", unsafe_allow_html=True)

    with harita_alan:
        if not secili:
            st.info("Soldan en az bir gün seçin.")
        else:
            tum = df[df.apply(lambda r: (r.employee, r.date) in secili, axis=1)
                     ].dropna(subset=["latitude","longitude"])
            if len(tum)==0:
                st.warning("Seçili günler için koordinat bulunamadı.")
            else:
                m = folium.Map(location=[tum.latitude.mean(), tum.longitude.mean()],
                               zoom_start=7)
                for (p, g) in secili:
                    rota_ciz(m, df[(df.employee==p)&(df.date==g)],
                             personel_renk(p), tooltip_on=f"{p} {g} — ")
                harita_goster(m, height=760, key="genel_map")
                lejand()
                toplam = sum(
                    (df[(df.employee==p)&(df.date==g)].stop_type=="Farm Visit").sum()
                    for p,g in secili)
                st.caption(f"Gösterilen: {len(secili)} gün · {int(toplam)} çiftlik ziyareti")

# ═══════════════════════════════════════════════════════════════
# SEKME 3 — TÜM TABLO
# ═══════════════════════════════════════════════════════════════
with sekme3:
    st.caption("Yönetim için: tüm veriyi filtreleyip inceleyin.")
    t1, t2 = st.columns(2)
    with t1:
        t_cal = st.multiselect("Çalışan", sorted(df.employee.unique()),
                               default=sorted(df.employee.unique()), key="t_cal")
    with t2:
        t_detay = st.checkbox("Tüm detay sütunlarını göster", value=False, key="t_detay")
    tdf = df[df.employee.isin(t_cal)]
    if not t_detay:
        tdf = tdf[["employee","date","stop_no","location","task",
                   "arrival","departure","time_on_site","break_taken","hotel"]]
    st.dataframe(tdf, use_container_width=True, hide_index=True, height=560)
    st.caption(f"{len(tdf)} satır")
