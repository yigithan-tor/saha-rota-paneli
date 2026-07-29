"""
Excel ciktisini SQLite'a yukler + her tarlaya bolge (kume) atar.
Kullanim:  python load_to_db.py optimized_151_25_days_with_sum.xlsx
Cikti:     routes.db  (Streamlit uygulamasinin okudugu dosya)

Bolge mantigi:
- Birbirine 50 km'den yakin tarlalar ayni kumeye girer (DBSCAN, haversine).
- Her kumenin merkezi (ortalama koordinat) hangi il sinirindaysa o ilin adini alir.
- Ayni ilde birden fazla kume varsa numaralanir (Balikesir 1, Balikesir 2).
- 3'ten az tarlasi olan kume "(outlier)" olarak etiketlenir.
"""
import sys
import sqlite3
import json
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.cluster import DBSCAN
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

# ── 2. Bolge hesabi (sadece ciftlikler uzerinden) ─────────────
def bolgeleri_hesapla(df):
    farms = (df[df.stop_type == "Farm Visit"][["location", "latitude", "longitude"]]
             .drop_duplicates().dropna().reset_index(drop=True))
    if len(farms) == 0:
        return {}

    # DBSCAN — 50 km esikli, haversine metrigi (radyan)
    coords = np.radians(farms[["latitude", "longitude"]].values)
    db = DBSCAN(eps=ESIK_KM / 6371.0, min_samples=1,
                metric="haversine").fit(coords)
    farms["k"] = db.labels_

    # Il sinirlarini yukle
    gj = json.load(open(IL_SINIRLARI, encoding="utf-8"))
    iller = [(f["properties"]["name"], shape(f["geometry"])) for f in gj["features"]]

    def il_bul(lat, lon):
        p = Point(lon, lat)
        for name, geom in iller:
            if geom.contains(p):
                return name
        return "Bilinmeyen"

    # Her kume: il + boyut
    kume = {}
    for k, g in farms.groupby("k"):
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

    # tarla -> bolge adi eslemesi
    return {row.location: kume[row.k]["ad"] for row in farms.itertuples()}

tarla_bolge = bolgeleri_hesapla(df)

# Her satira bolge yaz (ciftlik degilse bos)
df["bolge"] = df["location"].map(tarla_bolge).fillna("")

# ── 3. SQLite'a yaz ───────────────────────────────────────────
con = sqlite3.connect(DB)
df.to_sql("routes", con, if_exists="replace", index=False)
con.close()

# Ozet ciktisi
print(f"Yuklendi: {len(df)} satir -> {DB} (tablo: routes)")
if tarla_bolge:
    ozet = pd.Series(tarla_bolge).value_counts()
    print("Bolgeler:")
    for ad, n in ozet.items():
        print(f"  {ad}: {n} tarla")
