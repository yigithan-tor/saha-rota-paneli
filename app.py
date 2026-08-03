"""
Saha Rota Paneli — Streamlit uygulamasi
python -m streamlit run app.py
"""
import json
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
@st.cache_data(ttl=0)
def veriyi_yukle():
    con = sqlite3.connect("routes.db")
    df = pd.read_sql("SELECT * FROM routes", con)
    con.close()
    return df

df = veriyi_yukle()

# ── Her personel icin sabit renk ──────────────────────────────
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

# Home/otel dugumleri icin tek, notr renk
DUGUM_RENK = "#3a3a3a"   # koyu gri — tum ev/otel noktalari ayni

def gun_etiketi(day_type):
    if not isinstance(day_type, str): return ""
    if "Start"     in day_type: return "trip · başlangıç"
    if "Continues" in day_type: return "trip · devam"
    if "End"       in day_type: return "trip · son"
    return ""

def dugum_etiketi(satir):
    """Ev -> P, Otel -> otel kodu (H001 gibi)."""
    if satir.location == "Home":
        return "P"
    if satir.location == "Hotel":
        return satir.hotel if pd.notna(satir.hotel) else "H"
    return "?"

# ── Bir gunun rotasini haritaya cizer ────────────────────────
def rota_ciz(harita, gun_df, cizgi_renk, tooltip_on="", bolge_filtre=None):
    hd = gun_df.dropna(subset=["latitude", "longitude"]).sort_values("stop_no")
    if len(hd) == 0:
        return
    if bolge_filtre is not None:
        # bolge degeri bos olanlar (ev) her zaman kalir; Farm Visit ve otel
        # duraklari (ikisi de routes.db'de kendi bolge degerine sahip)
        # secili bolge listesine gore filtrelenir.
        hd = hd[(hd.bolge == "") | (hd.bolge.isin(bolge_filtre))]
        if len(hd) == 0:
            return

    # Ince cizgi + uzerinde kucuk yon oklari
    if bolge_filtre is None:
        segmentler = [hd]
    else:
        # Filtre yuzunden aradan cikan duraklar cizgiyi keser: sadece
        # orijinal stop_no'su ardisik olan duraklar arasinda cizgi cizilir.
        segmentler = []
        stop_no = hd.stop_no.tolist()
        baslangic = 0
        for i in range(1, len(hd)):
            if stop_no[i] - stop_no[i - 1] != 1:
                segmentler.append(hd.iloc[baslangic:i])
                baslangic = i
        segmentler.append(hd.iloc[baslangic:])

    for seg in segmentler:
        if len(seg) < 2:
            continue
        koord = list(zip(seg.latitude, seg.longitude))
        pl = folium.PolyLine(koord, color=cizgi_renk, weight=2,
                             opacity=0.85, tooltip=tooltip_on)
        pl.add_to(harita)
        PolyLineTextPath(
            pl, "          \u25B6          ", repeat=True, center=False, offset=3,
            attributes={"fill": cizgi_renk, "font-size": "7"},
        ).add_to(harita)

    # Isaretler
    for _, s in hd.iterrows():
        if s.stop_type == "Farm Visit":
            folium.CircleMarker(
                [s.latitude, s.longitude], radius=5,
                color="white", weight=1,
                fill=True, fill_color=cizgi_renk, fill_opacity=0.95,
                tooltip=f"{tooltip_on}{s.stop_no}. {s.location} ({s.arrival})",
            ).add_to(harita)
        else:
            # Ev/otel: tek renk
            etiket = dugum_etiketi(s)
            folium.CircleMarker(
                [s.latitude, s.longitude], radius=6,
                color="white", weight=1,
                fill=True, fill_color=DUGUM_RENK, fill_opacity=0.95,
                tooltip=f"{tooltip_on}{etiket} — {s.location} ({s.arrival})",
            ).add_to(harita)

@st.cache_data
def hafta_haritasi():
    tarihler = pd.to_datetime(sorted(df.date.unique()))
    iso = tarihler.isocalendar()
    haftalar = {}
    for n, wk in enumerate(sorted(set(iso.week)), start=1):
        gunler = [t for t, w in zip(tarihler, iso.week) if w == wk]
        haftalar[wk] = f"Hafta {n} ({min(gunler).strftime('%d')}–{max(gunler).strftime('%d')} Haz)"
    return {t.strftime("%Y-%m-%d"): haftalar[w] for t, w in zip(tarihler, iso.week)}

HAFTA = hafta_haritasi()

@st.cache_data
def gun_ozeti():
    rows = []
    for _, g in df[["employee","date"]].drop_duplicates().iterrows():
        gd = df[(df.employee==g.employee)&(df.date==g.date)].sort_values("stop_no")
        rows.append({
            "employee": g.employee, "date": g.date,
            "hafta":  HAFTA.get(g.date, ""),
            "tag":   gun_etiketi(gd.day_type.iloc[0]),
            "farms": int((gd.stop_type=="Farm Visit").sum()),
            "start": gd.arrival.iloc[0], "end": gd.arrival.iloc[-1],
        })
    return pd.DataFrame(rows)

OZET = gun_ozeti()

# ── Genel Harita: tamamen istemci tarafi (JS/Leaflet) harita ──
# Gun secimi, hafta filtresi ve bolge analizi artik tarayicida calisir;
# Streamlit sadece bu HTML'i bir iframe olarak gomer, etkilesimlerde
# Python'a geri donmez.
_GENEL_HARITA_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Genel Harita</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet-polylinedecorator/1.1.0/leaflet.polylineDecorator.min.js"></script>
<style>
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; height:100%;
               font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               color:#1c2128; }
  #app { display:flex; height:100%; }

  #sidebar { width:300px; min-width:300px; height:100%; overflow-y:auto;
             background:#fff; border-right:1px solid #e3e6ea; padding:12px; }
  #sidebar h3 { font-size:12px; margin:14px 0 6px; color:#555;
                text-transform:uppercase; letter-spacing:.03em; }
  #sidebar h3:first-child { margin-top:0; }

  .pill-row { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:6px; }
  .pill { font-size:11px; padding:3px 8px; border-radius:20px; border:1px solid #e3e6ea;
          background:#f6f7f9; color:#555; cursor:pointer; user-select:none; }
  .pill.on { background:#3a3a3a; color:#fff; border-color:#3a3a3a; }

  .switch-row { display:flex; align-items:center; gap:8px; font-size:12.5px;
                margin:6px 0 10px; cursor:pointer; }
  .switch { position:relative; width:34px; height:18px; background:#d7dae0;
            border-radius:20px; transition:background .15s; flex-shrink:0; }
  .switch.on { background:#3a3a3a; }
  .switch::after { content:''; position:absolute; top:2px; left:2px; width:14px; height:14px;
                    border-radius:50%; background:#fff; transition:left .15s; }
  .switch.on::after { left:18px; }

  .person-block { margin-bottom:10px; border:1px solid #e3e6ea; border-radius:10px; overflow:hidden; }
  .person-header { padding:9px 11px; display:flex; align-items:center; gap:8px; background:#f6f7f9; }
  .person-dot { width:10px; height:10px; border-radius:3px; flex-shrink:0; }
  .person-name { font-weight:700; font-size:13px; flex:1; }
  .person-meta { font-size:10.5px; color:#8a877d; }
  .toggle-all { font-size:10.5px; color:#8a877d; text-decoration:underline; cursor:pointer; }
  .toggle-all:hover { color:#1c2128; }

  .day-list { padding:5px 7px 7px; }
  .day-row { display:flex; align-items:flex-start; gap:8px; padding:6px 6px; font-size:12px;
             border-radius:8px; cursor:pointer; }
  .day-row:hover { background:#f6f7f9; }
  .day-row.hidden { display:none; }
  input[type=checkbox] { accent-color:#1c2128; cursor:pointer; width:13px; height:13px;
                          flex-shrink:0; margin-top:2px; }
  .swatch { width:10px; height:10px; border-radius:3px; flex-shrink:0; margin-top:3px; }
  .day-info { flex:1; min-width:0; }
  .day-date { font-weight:500; font-size:12.5px; }
  .day-tag { color:#b8860b; font-size:10px; }
  .day-sub { color:#8a877d; font-size:11px; margin-top:1px; }

  #map-wrap { flex:1; position:relative; height:100%; }
  #map { width:100%; height:100%; }
  #status { position:absolute; left:10px; bottom:10px; z-index:15; background:rgba(255,255,255,.95);
            border:1px solid #e3e6ea; border-radius:8px; padding:5px 10px; font-size:11.5px; color:#555; }
  #legend { position:absolute; right:10px; bottom:10px; z-index:15; background:rgba(255,255,255,.96);
            border:1px solid #e3e6ea; border-radius:10px; padding:9px 11px; font-size:11.5px; color:#555;
            line-height:1.7; max-width:230px; }

  .num-badge {
    display:flex; align-items:center; justify-content:center; color:#fff; font-weight:700;
    border-radius:50%; border:2px solid #fff; box-shadow:0 0 3px rgba(0,0,0,.55);
    font-family:sans-serif; box-sizing:border-box;
  }
  .leaflet-tooltip { font-size:11.5px; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h3>Hafta filtresi</h3>
    <div class="pill-row" id="hafta-pills"></div>

    <div class="switch-row" id="bolge-switch-row">
      <div class="switch" id="bolge-switch"></div>
      <span>Bölge Analizi</span>
    </div>
    <div class="pill-row" id="bolge-pills" style="display:none;"></div>

    <h3>Günler</h3>
    <div id="controls"></div>
  </div>
  <div id="map-wrap">
    <div id="map"></div>
    <div id="status"></div>
    <div id="legend"></div>
  </div>
</div>

<script id="route-data" type="application/json">__ROUTE_DATA_JSON__</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('route-data').textContent);

  const map = L.map('map', { zoomControl: true }).setView([39.5, 30], 7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  // Streamlit gizli sekmeleri de DOM'da tutar (display:none), yani harita
  // sekme aktif olmadan once 0x0 boyutla ilklendirilebilir ve karo/katmanlar
  // hic cizilmez. Konteynerin gercek boyutu degistiginde (orn. sekme
  // acildiginda) Leaflet'e haber verip yeniden olceklendiriyoruz.
  const mapEl = document.getElementById('map');
  let ilkGorunumYapildi = false;
  function konteynerBoyutuDegisti() {
    map.invalidateSize();
    if (!ilkGorunumYapildi && mapEl.offsetWidth > 0 && mapEl.offsetHeight > 0) {
      ilkGorunumYapildi = true;
      ilkGorunumeSigdir();
    }
  }
  if (window.ResizeObserver) {
    new ResizeObserver(konteynerBoyutuDegisti).observe(mapEl);
  } else {
    window.addEventListener('resize', konteynerBoyutuDegisti);
  }

  const state = {
    checked: new Set(),
    hafta: new Set(DATA.haftalar.map(h => h.key)),
    bolgeOn: false,
    bolge: new Set(DATA.bolgeler),
  };
  DATA.employees.forEach(emp => emp.days.forEach(d => state.checked.add(emp.name + '|' + d.date)));

  let currentLayers = [];

  function splitConsecutive(stops) {
    const segs = [];
    let cur = [];
    for (const s of stops) {
      if (cur.length === 0 || s.stopNo - cur[cur.length - 1].stopNo === 1) {
        cur.push(s);
      } else {
        segs.push(cur);
        cur = [s];
      }
    }
    if (cur.length) segs.push(cur);
    return segs;
  }

  function badgeIcon(text, bg, size, fontSize) {
    return L.divIcon({
      className: '',
      html: '<div class="num-badge" style="background:' + bg + ';width:' + size + 'px;height:' +
            size + 'px;font-size:' + fontSize + 'px;">' + text + '</div>',
      iconSize: [size, size], iconAnchor: [size / 2, size / 2],
    });
  }

  function buildDayLayer(emp, day) {
    let stops = day.stops;
    if (state.bolgeOn) {
      stops = stops.filter(s => s.bolge === '' || state.bolge.has(s.bolge));
    }
    if (stops.length === 0) return null;

    const layers = [];
    for (const seg of splitConsecutive(stops)) {
      if (seg.length < 2) continue;
      const latlngs = seg.map(s => [s.lat, s.lng]);
      const line = L.polyline(latlngs, { color: emp.color, weight: 2, opacity: 0.85 });
      layers.push(line);
      layers.push(L.polylineDecorator(line, {
        patterns: [{ offset: 12, repeat: 60, symbol: L.Symbol.arrowHead({
          pixelSize: 7, polygon: true,
          pathOptions: { color: emp.color, fillColor: emp.color, fillOpacity: 1, weight: 0 }
        }) }]
      }));
    }
    for (const s of stops) {
      const icon = s.isFarm
        ? badgeIcon(s.label, emp.color, 18, 10)
        : badgeIcon(s.label, DATA.dugumRenk, 20, 9);
      // Bazi gunlerde "Hotel" tipli bir durak, calisanin ev koordinatiyla
      // birebir aynidir (cok gunlu gorevin baslangic/bitisi evde). Ayni
      // pikselde ust uste binince Leaflet en son eklenen katmani ustte
      // gosterir; ev (P) her zaman otelin (H...) ustunde kalsin diye
      // zIndexOffset ile sirayi veriye degil tipe gore sabitliyoruz.
      const zIndexOffset = s.isFarm ? 0 : (s.isHome ? 1000 : -1000);
      layers.push(L.marker([s.lat, s.lng], { icon, zIndexOffset }).bindTooltip(s.tooltip, { sticky: true }));
    }
    return L.layerGroup(layers);
  }

  function renderMap() {
    currentLayers.forEach(l => map.removeLayer(l));
    currentLayers = [];
    let gunSayisi = 0, ciftlikSayisi = 0;
    DATA.employees.forEach(emp => {
      emp.days.forEach(day => {
        const key = emp.name + '|' + day.date;
        if (!state.checked.has(key) || !state.hafta.has(day.hafta)) return;
        const layer = buildDayLayer(emp, day);
        if (!layer) return;
        layer.addTo(map);
        currentLayers.push(layer);
        gunSayisi++;
        if (state.bolgeOn) {
          ciftlikSayisi += day.stops.filter(s => s.isFarm && (s.bolge === '' || state.bolge.has(s.bolge))).length;
        } else {
          ciftlikSayisi += day.farms;
        }
      });
    });
    document.getElementById('status').textContent =
      'Gösterilen: ' + gunSayisi + ' gün · ' + ciftlikSayisi + ' çiftlik ziyareti';
  }

  /* ---------- hafta pills ---------- */
  const haftaPillsEl = document.getElementById('hafta-pills');
  DATA.haftalar.forEach(h => {
    const pill = document.createElement('div');
    pill.className = 'pill on';
    pill.textContent = h.label;
    pill.addEventListener('click', () => {
      if (state.hafta.has(h.key)) { state.hafta.delete(h.key); pill.classList.remove('on'); }
      else { state.hafta.add(h.key); pill.classList.add('on'); }
      applyHaftaVisibility();
      renderMap();
    });
    haftaPillsEl.appendChild(pill);
  });

  function applyHaftaVisibility() {
    document.querySelectorAll('.day-row').forEach(row => {
      row.classList.toggle('hidden', !state.hafta.has(row.dataset.hafta));
    });
  }

  /* ---------- bolge toggle + pills ---------- */
  const bolgeSwitchRow = document.getElementById('bolge-switch-row');
  const bolgeSwitch = document.getElementById('bolge-switch');
  const bolgePillsEl = document.getElementById('bolge-pills');
  DATA.bolgeler.forEach(b => {
    const pill = document.createElement('div');
    pill.className = 'pill on';
    pill.textContent = b;
    pill.addEventListener('click', () => {
      if (state.bolge.has(b)) { state.bolge.delete(b); pill.classList.remove('on'); }
      else { state.bolge.add(b); pill.classList.add('on'); }
      renderMap();
    });
    bolgePillsEl.appendChild(pill);
  });
  bolgeSwitchRow.addEventListener('click', () => {
    state.bolgeOn = !state.bolgeOn;
    bolgeSwitch.classList.toggle('on', state.bolgeOn);
    bolgePillsEl.style.display = state.bolgeOn ? 'flex' : 'none';
    renderMap();
  });

  /* ---------- person / day rows ---------- */
  const controlsEl = document.getElementById('controls');
  DATA.employees.forEach(emp => {
    const block = document.createElement('div');
    block.className = 'person-block';

    const header = document.createElement('div');
    header.className = 'person-header';
    header.innerHTML =
      '<span class="person-dot" style="background:' + emp.color + '"></span>' +
      '<span class="person-name">' + emp.name + '</span>' +
      '<span class="person-meta">' + emp.days.length + ' gün</span>' +
      '<span class="toggle-all">toggle all</span>';
    header.querySelector('.toggle-all').addEventListener('click', () => {
      const boxes = block.querySelectorAll('.day-row:not(.hidden) input[type=checkbox]');
      const allOn = Array.from(boxes).every(cb => cb.checked);
      boxes.forEach(cb => {
        cb.checked = !allOn;
        if (cb.checked) state.checked.add(cb.dataset.key); else state.checked.delete(cb.dataset.key);
      });
      renderMap();
    });
    block.appendChild(header);

    const dayList = document.createElement('div');
    dayList.className = 'day-list';
    emp.days.forEach(day => {
      const key = emp.name + '|' + day.date;
      const row = document.createElement('div');
      row.className = 'day-row';
      row.dataset.hafta = day.hafta;
      row.innerHTML =
        '<input type="checkbox" data-key="' + key + '" checked>' +
        '<span class="swatch" style="background:' + emp.color + '"></span>' +
        '<div class="day-info">' +
          '<div class="day-date">' + day.date +
            (day.tag ? ' <span class="day-tag">(' + day.tag + ')</span>' : '') +
          '</div>' +
          '<div class="day-sub">' + day.farms + ' durak · ' + day.start + '–' + day.end + '</div>' +
        '</div>';
      const cb = row.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) state.checked.add(key); else state.checked.delete(key);
        renderMap();
      });
      row.addEventListener('click', (e) => {
        if (e.target === cb) return;
        const pts = day.stops.map(s => [s.lat, s.lng]);
        if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 13 });
      });
      dayList.appendChild(row);
    });
    block.appendChild(dayList);
    controlsEl.appendChild(block);
  });

  /* ---------- legend ---------- */
  document.getElementById('legend').innerHTML =
    '<b>Gösterim</b><br>' +
    'çizgi + oklar = rota ve yön<br>' +
    'sayılı daire = ziyaretin günü (ay içinde)<br>' +
    '<span style="background:' + DATA.dugumRenk + ';color:#fff;padding:0 5px;border-radius:8px;">P</span> personel evi &nbsp; ' +
    '<span style="background:' + DATA.dugumRenk + ';color:#fff;padding:0 5px;border-radius:8px;">H…</span> otel';

  /* ---------- ilk yukleme ---------- */
  // Sekme baslangicta gizliyse konteyner 0x0'dir; boyuta gore sinirlara
  // oturtma islemini konteynerBoyutuDegisti() (ResizeObserver) tetikler.
  // Sekme zaten aciksa (gizli degilse) burada hemen calisir.
  function ilkGorunumeSigdir() {
    const allPts = [];
    DATA.employees.forEach(emp => emp.days.forEach(d => d.stops.forEach(s => allPts.push([s.lat, s.lng]))));
    if (allPts.length) map.fitBounds(L.latLngBounds(allPts), { padding: [30, 30] });
  }
  renderMap();
  if (mapEl.offsetWidth > 0 && mapEl.offsetHeight > 0) {
    ilkGorunumYapildi = true;
    ilkGorunumeSigdir();
  }
})();
</script>
</body>
</html>
"""

_AY_KISA = ["", "Oca", "Şub", "Mar", "Nis", "May", "Haz",
            "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]

def _hafta_bilgisi(tarih_str):
    """ISO haftasinin Pazartesi-Pazar tam araligini dondurur — o hafta
    icinde veri olmayan gunler de dahil, sadece calisma gunlerinin
    min/max'i degil. Donus: (anahtar, etiket)."""
    gun = pd.Timestamp(tarih_str)
    pazartesi = gun - pd.Timedelta(days=gun.isoweekday() - 1)
    pazar = pazartesi + pd.Timedelta(days=6)
    if pazartesi.month == pazar.month:
        etiket = f"{pazartesi.day:02d}–{pazar.day:02d} {_AY_KISA[pazartesi.month]}"
    else:
        etiket = (f"{pazartesi.day:02d} {_AY_KISA[pazartesi.month]}–"
                  f"{pazar.day:02d} {_AY_KISA[pazar.month]}")
    iso_yil, iso_hafta, _ = gun.isocalendar()
    anahtar = f"{iso_yil}-W{iso_hafta:02d}"
    return anahtar, etiket

def genel_harita_html(df):
    """Genel Harita sekmesi icin tum veriyi tek bir JSON'a gomup,
    tamamen istemci tarafinda calisan bir Leaflet HTML'i uretir."""
    hafta_etiketleri = dict(_hafta_bilgisi(t) for t in df.date.unique())
    calisanlar = []
    for personel in sorted(df.employee.unique()):
        renk = personel_renk(personel)
        gunler = []
        p_ozet = OZET[OZET.employee == personel].sort_values("date")
        for _, oz in p_ozet.iterrows():
            gd = (df[(df.employee == personel) & (df.date == oz.date)]
                  .dropna(subset=["latitude", "longitude"]).sort_values("stop_no"))
            if len(gd) == 0:
                continue
            gun_no = int(str(oz.date).split("-")[2])
            tooltip_on = f"{personel} {oz.date} — "
            duraklar = []
            for _, s in gd.iterrows():
                is_farm = s.stop_type == "Farm Visit"
                if is_farm:
                    etiket = str(gun_no)
                    tooltip = f"{tooltip_on}{s.stop_no}. {s.location} ({s.arrival})"
                else:
                    etiket = dugum_etiketi(s)
                    tooltip = f"{tooltip_on}{etiket} — {s.location} ({s.arrival})"
                duraklar.append({
                    "stopNo": int(s.stop_no),
                    "isFarm": is_farm,
                    "isHome": s.location == "Home",
                    "label": etiket,
                    "lat": float(s.latitude),
                    "lng": float(s.longitude),
                    "bolge": s.bolge if isinstance(s.bolge, str) else "",
                    "tooltip": tooltip,
                })
            hafta_anahtari, _ = _hafta_bilgisi(oz.date)
            gunler.append({
                "date": oz.date,
                "hafta": hafta_anahtari,
                "tag": oz.tag,
                "farms": int(oz.farms),
                "start": oz.start,
                "end": oz.end,
                "stops": duraklar,
            })
        if gunler:
            calisanlar.append({"name": personel, "color": renk, "days": gunler})

    tum_haftalar = [{"key": k, "label": v} for k, v in sorted(hafta_etiketleri.items())]
    tum_bolgeler = sorted(b for b in df.bolge.unique() if isinstance(b, str) and b)

    payload = {
        "employees": calisanlar,
        "haftalar": tum_haftalar,
        "bolgeler": tum_bolgeler,
        "dugumRenk": DUGUM_RENK,
    }
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return _GENEL_HARITA_TEMPLATE.replace("__ROUTE_DATA_JSON__", payload_json)

# ── Kucuk aciklama (harita lejandi) ───────────────────────────
def lejand():
    st.markdown(
        "<div style='font-size:12px;color:#555;line-height:1.6'>"
        "<b>Gösterim:</b> çizgi + küçük oklar = rota ve gidiş yönü &nbsp;|&nbsp; "
        "renkli nokta = çiftlik ziyareti (rota rengiyle) &nbsp;|&nbsp; "
        "<span style='background:#3a3a3a;color:white;padding:0 5px;border-radius:8px'>●</span> "
        "ev/otel &nbsp;— detay için noktaların üzerine gelin (tooltip)"
        "</div>", unsafe_allow_html=True)

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
    mola = "Var" if (gd.break_taken=="Yes").any() else "Yok"
    otel = gd.hotel.iloc[0] if len(gd) and pd.notna(gd.hotel.iloc[0]) else "-"

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Çiftlik ziyareti", int(farm))
    k2.metric("Gün başlangıcı",   gd.arrival.iloc[0] if len(gd) else "-")
    k3.metric("Gün bitişi",       gd.arrival.iloc[-1] if len(gd) else "-")
    k4.metric("Öğle molası",      mola)
    k5.metric("Konaklama",        otel)

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
    st.caption("Yönetim ve test için: gün seçimi, hafta filtresi ve bölge analizi haritanın "
               "içinde — etkileşimler Streamlit'e geri dönmez.")
    components.html(genel_harita_html(df), height=760)

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
