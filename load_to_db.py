"""
Excel ciktisini SQLite'a yukler.
Kullanim:  python load_to_db.py optimized_151_25_days_with_sum.xlsx
Cikti:     routes.db  (Streamlit uygulamasinin okudugu dosya)

Bu adim su an manuel. Ileride Lokman script'in sonuna
ayni tabloyu dogrudan SQLite'a yazan birkac satir eklerse
bu adima hic gerek kalmaz.
"""
import sys
import sqlite3
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "route_data.xlsx"
DB = "routes.db"

# 'Route Schedule' sekmesindeki tum ham satirlari oku
df = pd.read_excel(SRC, sheet_name="Route Schedule")

# Sutun adlarini sadelestir (bosluk/isaret temizligi -> kolay sorgu)
df.columns = [
    "employee", "date", "day_type", "working_day", "stop_no",
    "stop_type", "location", "task", "travel_min", "arrival",
    "service_start", "service_end", "departure", "time_on_site",
    "break_taken", "break_start", "break_end", "hotel",
    "trip_day", "actual_home_arrival", "late_return",
    "latitude", "longitude",
]

# Tarihi tek tip metne cevir (2026-06-01)
df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

con = sqlite3.connect(DB)
df.to_sql("routes", con, if_exists="replace", index=False)
con.close()

print(f"Yuklendi: {len(df)} satir -> {DB} (tablo: routes)")
