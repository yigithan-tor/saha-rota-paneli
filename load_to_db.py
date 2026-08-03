"""
Excel ciktisini SQLite'a yukler + her tarlaya ve otele bolge (kume) atar.
Kullanim:  python load_to_db.py route_data.xlsx
Cikti:     routes.db  (Streamlit uygulamasinin okudugu dosya)

Bolge mantigi:
- Birbirine 50 km'den yakin tarlalar ayni kumeye girer (DBSCAN, haversine).
- Her kumenin merkezi (ortalama koordinat) hangi il sinirindaysa o ilin adini alir.
- Ayni ilde birden fazla kume varsa numaralanir (Balikesir 1, Balikesir 2).
- 3'ten az tarlasi olan kume "(outlier)" olarak etiketlenir.
- Oteller ayri kumelenmez: her otel, koordinat olarak en yakin ciftligin
  bolgesine atanir (o ciftligin ait oldugu kumeyi devralir).
"""
import sys
import sqlite3
import json
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.cluster import DBSCAN
from sklearn.neighbors import BallTree
from shapely.geometry import Point, shape

SRC = sys.argv[1] if len(sys.argv) > 1 else "route_data.xlsx"
DB = "routes.db"
IL_SINIRLARI = "turkey_provinces.json"

ESIK_KM = 50        # bu mesafeden yakin tarlalar ayni bolgede
OUTLIER_ALTI = 3    # bu sayidan az tarlasi olan bolge outlier

# ── 1. Excel'i oku ────────────────────────────────────────────
df = pd.read_excel(SRC, sheet_name="Route Schedule")
df.columns = [
    "employee", "date", "day_type", "working_day", "stop_no",
    "stop_type", "location", "task", "travel_min", "arrival",
    "service_start", "service_end", "departure", "time_on_site",
    "break_taken", "break_start", "break_end", "hotel",
    "trip_day", "actual_home_arrival", "late_return",
    "latitude", "longitude",
]
df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

# ── 2. Bolge hesabi ─────────────────────────────────────────────
# Il sinirlarini bir kez yukle (sadece ciftlik kumelemesinde kullanilir;
# oteller kendi il tespiti yapmaz, en yakin ciftligin bolgesini devralir)
gj = json.load(open(IL_SINIRLARI, encoding="utf-8"))
iller = [(f["properties"]["name"], shape(f["geometry"])) for f in gj["features"]]

def il_bul(lat, lon):
    p = Point(lon, lat)
    for name, geom in iller:
        if geom.contains(p):
            return name
    return "Bilinmeyen"

def bolge_kumele(noktalar):
    """noktalar: essiz ['id','latitude','longitude'] satirlari.
    DBSCAN (50 km, haversine) + il siniri kontroluyle her id'ye bolge adi atar."""
    if len(noktalar) == 0:
        return {}

    coords = np.radians(noktalar[["latitude", "longitude"]].values)
    db = DBSCAN(eps=ESIK_KM / 6371.0, min_samples=1,
                metric="haversine").fit(coords)
    noktalar = noktalar.copy()
    noktalar["k"] = db.labels_

    # Her kume: il + boyut
    kume = {}
    for k, g in noktalar.groupby("k"):
        kume[k] = {"il": il_bul(g.latitude.mean(), g.longitude.mean()),
                   "boyut": len(g)}

    # Ayni ilde kac kume var (akilli numara icin)
    il_kume_sayisi = Counter(v["il"] for v in kume.values())

    # Isim uret
    il_sayac = {}
    for k in sorted(kume):
        il, boyut = kume[k]["il"], kume[k]["boyut"]
        if il_kume_sayisi[il] > 1:
            il_sayac[il] = il_sayac.get(il, 0) + 1
            ad = f"{il} {il_sayac[il]}"
        else:
            ad = il
        if boyut < OUTLIER_ALTI:
            ad += " (outlier)"
        kume[k]["ad"] = ad

    # id -> bolge adi eslemesi
    return {row.id: kume[row.k]["ad"] for row in noktalar.itertuples()}

def en_yakin_ciftlik_bolgesi(noktalar, farms, tarla_bolge):
    """noktalar: essiz ['id','latitude','longitude'] satirlari (ornegin oteller).
    Ayri kumeleme yapmaz — her noktayi, koordinat olarak en yakin ciftligin
    zaten atanmis oldugu bolgeye baglar."""
    if len(noktalar) == 0 or len(farms) == 0:
        return {}

    agac = BallTree(np.radians(farms[["latitude", "longitude"]].values),
                     metric="haversine")
    _, idx = agac.query(np.radians(noktalar[["latitude", "longitude"]].values), k=1)
    en_yakin_ciftlik = farms["id"].values[idx[:, 0]]
    return {row.id: tarla_bolge[loc]
            for row, loc in zip(noktalar.itertuples(), en_yakin_ciftlik)}

farms = (df[df.stop_type == "Farm Visit"][["location", "latitude", "longitude"]]
         .drop_duplicates().dropna().reset_index(drop=True)
         .rename(columns={"location": "id"}))
tarla_bolge = bolge_kumele(farms)

def _otel_anahtari(hotel, lat, lon):
    """'hotel' kodu (orn. H001) tek basina essiz degildir — ayni kod farkli
    koordinatlarda (hatta bazen personel evinde) tekrar kullanilabiliyor.
    Kod + koordinat bilesimini anahtar yaparak her fiziksel noktayi ayirt ederiz."""
    return hotel.astype(str) + "@" + lat.round(6).astype(str) + "," + lon.round(6).astype(str)

hotels = (df[df.location == "Hotel"][["hotel", "latitude", "longitude"]]
          .drop_duplicates().dropna().reset_index(drop=True))
hotels["id"] = _otel_anahtari(hotels.hotel, hotels.latitude, hotels.longitude)
otel_bolge = en_yakin_ciftlik_bolgesi(hotels, farms, tarla_bolge)

# Her satira bolge yaz: ciftlik -> tarla_bolge, otel durak -> otel_bolge, digerleri bos
df["bolge"] = ""
df.loc[df.stop_type == "Farm Visit", "bolge"] = \
    df.loc[df.stop_type == "Farm Visit", "location"].map(tarla_bolge)
otel_maske = df.location == "Hotel"
df.loc[otel_maske, "bolge"] = _otel_anahtari(
    df.loc[otel_maske, "hotel"], df.loc[otel_maske, "latitude"], df.loc[otel_maske, "longitude"]
).map(otel_bolge)
df["bolge"] = df["bolge"].fillna("")

# ── 3. SQLite'a yaz ───────────────────────────────────────────
con = sqlite3.connect(DB)
df.to_sql("routes", con, if_exists="replace", index=False)
con.close()

# Ozet ciktisi
print(f"Yuklendi: {len(df)} satir -> {DB} (tablo: routes)")
if tarla_bolge:
    ozet = pd.Series(tarla_bolge).value_counts()
    print("Ciftlik bolgeleri:")
    for ad, n in ozet.items():
        print(f"  {ad}: {n} tarla")
if otel_bolge:
    ozet = pd.Series(otel_bolge).value_counts()
    print("Otel bolgeleri:")
    for ad, n in ozet.items():
        print(f"  {ad}: {n} otel")
