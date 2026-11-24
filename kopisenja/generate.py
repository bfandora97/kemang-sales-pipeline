"""Generate FICTIONAL daily sales exports for "Kopi Senja", a made-up coffee shop.

Each source looks like a real export, with its own quirks (on purpose):
  kasir_kemang.csv  semicolon separated, dd/mm/yyyy dates, nicknames ("Es Kopsu"), ~1% duplicated rows
  kasir_tebet.csv   comma separated, ISO dates, UPPERCASE names, stray spaces
  gofood.csv        one row per order item, timestamp column, app menu names
  shopee.xlsx       Excel, marketplace product titles

Deterministic: the same date always produces the same files (seeded by the date),
so the pipeline can rebuild any history from scratch. All data is fictional.
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_alias, load_produk

HOURS = np.arange(7, 23)
HOUR_W = np.array([3, 5, 6, 5, 6, 8, 7, 6, 10, 13, 14, 12, 8, 6, 4, 2], float)
WEIGHT = {  # relative popularity
    "Es Kopi Susu Senja": 30, "Kopi Aren Literan 1L": 4, "Americano": 12, "Cafe Latte": 12, "Matcha Latte": 8,
    "Croissant Butter": 9, "Roti Bakar Cokelat": 6, "Kopi Bubuk Senja 250g": 3, "Red Velvet Latte": 1.2,
    "Kue Lumpur Pandan": 0.9,
}
BASE = {"kasir_kemang": 80, "kasir_tebet": 55, "gofood": 42, "shopee": 6}  # transactions per day


def _rng(d, sumber):
    return np.random.default_rng(int(d.strftime("%Y%m%d")) * 10 + list(BASE).index(sumber))


def _lines(d, sumber, alias, harga):
    rng = _rng(d, sumber)
    menu = alias[alias.sumber == sumber]
    w = np.array([WEIGHT[p] for p in menu.produk])
    wk = 1.25 if d.weekday() >= 5 and sumber != "shopee" else 1.0
    n = rng.poisson(BASE[sumber] * wk)
    rows = []
    for i in range(n):
        k = rng.choice(len(menu), p=w / w.sum())
        qty = int(1 + rng.poisson(0.35))
        hour = int(rng.choice(HOURS, p=HOUR_W / HOUR_W.sum()))
        minute = int(rng.integers(0, 60))
        nama, produk = menu.nama_asli.iloc[k], menu.produk.iloc[k]
        rows.append(dict(i=i, jam=hour, menit=minute, nama=nama, qty=qty, total=qty * harga[produk]))
    return pd.DataFrame(rows, columns=["i", "jam", "menit", "nama", "qty", "total"]), rng


def generate_day(d, folder):
    """Write the 4 export files for date d into folder/YYYY-MM-DD/. Returns the folder."""
    alias, harga = load_alias(), load_produk().set_index("produk").harga.to_dict()
    out = Path(folder) / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    tag = d.strftime("%y%m%d")

    df, rng = _lines(d, "kasir_kemang", alias, harga)
    k = pd.DataFrame({
        "No Struk": [f"KMG-{tag}-{x:04d}" for x in df.i],
        "Tanggal": d.strftime("%d/%m/%Y"),
        "Jam": [f"{h:02d}:{m:02d}" for h, m in zip(df.jam, df.menit)],
        "Nama Item": df.nama, "Qty": df.qty, "Total": df.total})
    dup = k.sample(frac=0.01, random_state=int(tag)) if len(k) else k  # export glitch: duplicated rows
    pd.concat([k, dup]).to_csv(out / "kasir_kemang.csv", sep=";", index=False)

    df, rng = _lines(d, "kasir_tebet", alias, harga)
    pd.DataFrame({
        "receipt_no": [f"TBT{tag}{x:04d}" for x in df.i],
        "date": d.isoformat(),
        "time": [f"{h:02d}:{m:02d}:00" for h, m in zip(df.jam, df.menit)],
        "item": [("  " + n) if j % 7 == 0 else (n + " ") if j % 5 == 0 else n for j, n in enumerate(df.nama)],
        "qty": df.qty, "amount": df.total}).to_csv(out / "kasir_tebet.csv", index=False)

    df, rng = _lines(d, "gofood", alias, harga)
    pd.DataFrame({
        "Order ID": [f"F-{tag}{x:05d}" for x in df.i],
        "Order Time": [f"{d.isoformat()} {h:02d}:{m:02d}:00" for h, m in zip(df.jam, df.menit)],
        "Item Name": df.nama, "Quantity": df.qty, "Gross Sales": df.total}).to_csv(out / "gofood.csv", index=False)

    df, rng = _lines(d, "shopee", alias, harga)
    pd.DataFrame({
        "No. Pesanan": [f"{tag}SP{x:05d}" for x in df.i],
        "Waktu Pesanan Dibuat": [f"{d.isoformat()} {h:02d}:{m:02d}" for h, m in zip(df.jam, df.menit)],
        "Nama Produk": df.nama, "Jumlah": df.qty, "Total Harga Produk": df.total}).to_excel(out / "shopee.xlsx", index=False)
    return out


def generate_range(start, end, folder):
    d = start
    while d <= end:
        if not (Path(folder) / d.isoformat() / "shopee.xlsx").exists():
            generate_day(d, folder)
        d += timedelta(days=1)


if __name__ == "__main__":
    import sys
    end = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    generate_range(end - timedelta(days=6), end, "data/raw")
    print("ok")
