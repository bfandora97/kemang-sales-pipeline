"""Run the whole pipeline: generate (fictional) exports -> load raw -> SQL -> quality checks -> outputs.

    python -m kopisenja.run                     # last 90 days up to today (Jakarta time)
    python -m kopisenja.run --sampai 2026-11-24 --hari 30

Fails (exit code 1) if any data-quality check fails, so a bad night never reaches the report.
Idempotent: every run rebuilds all tables from the raw files.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .config import load_alias, load_channel, load_produk
from .generate import generate_range

ROOT = Path(__file__).resolve().parent.parent
SQL = Path(__file__).resolve().parent / "sql"
WIB = timezone(timedelta(hours=7))
SOURCES = {"kasir_kemang": ("kasir_kemang.csv", dict(sep=";")), "kasir_tebet": ("kasir_tebet.csv", {}),
           "gofood": ("gofood.csv", {}), "shopee": ("shopee.xlsx", None)}


def load_raw(con, raw, start, end):
    """Read every export file as TEXT (no guessing) into raw_<source> tables."""
    counts = {}
    for sumber, (fname, opts) in SOURCES.items():
        frames = []
        d = start
        while d <= end:
            f = raw / d.isoformat() / fname
            df = pd.read_excel(f, dtype=str) if opts is None else pd.read_csv(f, dtype=str, keep_default_na=False, **opts)
            frames.append(df)
            d += timedelta(days=1)
        df = pd.concat(frames, ignore_index=True)
        counts[sumber] = len(df)
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE raw_{sumber} AS SELECT * FROM tmp")
        con.unregister("tmp")
    for name, df in (("ref_produk", load_produk()), ("ref_alias", load_alias()), ("ref_channel", load_channel())):
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    return counts


def quality(con, start, end):
    """Data-quality checks. Returns (list of (name, ok, detail), numbers for the report)."""
    q = lambda s: con.execute(s).fetchone()[0]
    checks = []
    unmapped = con.execute("""
        SELECT s.sumber, s.nama_asli, count(*) FROM stg_unik s
        LEFT JOIN ref_alias a ON a.sumber = s.sumber AND lower(a.nama_asli) = lower(s.nama_asli)
        WHERE a.produk IS NULL GROUP BY ALL""").fetchall()
    checks.append(("every product name is recognised", not unmapped, "; ".join(f"{s}: '{n}' x{c}" for s, n, c in unmapped)))
    stg, fact = q("SELECT sum(omzet) FROM stg_unik"), q("SELECT sum(omzet) FROM fact_penjualan")
    checks.append(("revenue reconciles (clean = fact)", stg == fact, f"{stg} vs {fact}"))
    bad = q("SELECT count(*) FROM stg_unik WHERE qty <= 0 OR omzet <= 0 OR waktu IS NULL")
    checks.append(("no empty/negative quantities, amounts or timestamps", bad == 0, f"{bad} rows"))
    days = (end - start).days + 1
    gaps = con.execute(f"""
        SELECT sumber, count(DISTINCT CAST(waktu AS DATE)) AS d FROM stg_unik
        WHERE sumber <> 'shopee' GROUP BY sumber HAVING d < {days}""").fetchall()
    checks.append(("every store channel has data for every day", not gaps, "; ".join(f"{s}: {d}/{days} days" for s, d in gaps)))
    out_range = q(f"SELECT count(*) FROM stg_unik WHERE CAST(waktu AS DATE) NOT BETWEEN DATE '{start}' AND DATE '{end}'")
    checks.append(("all dates inside the requested period", out_range == 0, f"{out_range} rows"))
    nums = dict(
        baris_mentah=q("SELECT count(*) FROM stg_penjualan"),
        baris_dobel_dibuang=q("SELECT (SELECT count(*) FROM stg_penjualan) - (SELECT count(*) FROM stg_unik)"),
        nama_produk_berbeda=q("SELECT count(DISTINCT sumber || '|' || nama_asli) FROM stg_unik"),
        produk_baku=q("SELECT count(DISTINCT produk) FROM fact_penjualan"),
    )
    return checks, nums


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sampai", type=date.fromisoformat, default=datetime.now(WIB).date())
    ap.add_argument("--hari", type=int, default=90)
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    a = ap.parse_args(argv)
    end, start = a.sampai, a.sampai - timedelta(days=a.hari - 1)

    generate_range(start, end, a.raw)
    con = duckdb.connect()
    counts = load_raw(con, a.raw, start, end)
    for f in sorted(SQL.glob("*.sql")):
        con.execute(f.read_text(encoding="utf-8"))
    checks, nums = quality(con, start, end)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if not ok else ""))
    if not all(ok for _, ok, _ in checks):
        sys.exit("Data quality failed: report NOT updated.")

    a.out.mkdir(parents=True, exist_ok=True)
    for t in ("mart_channel_bulanan", "mart_produk", "mart_jam", "mart_harian"):
        con.execute(f"SELECT * FROM {t}").df().to_csv(a.out / f"{t}.csv", index=False)
    ch = con.execute("""SELECT channel, sum(omzet) omzet, sum(laba) laba, round(sum(laba)*100.0/sum(omzet),1) margin
                        FROM fact_penjualan GROUP BY channel ORDER BY omzet DESC""").df()
    top = con.execute("SELECT produk, terjual, omzet FROM mart_produk ORDER BY omzet DESC LIMIT 5").df()
    slow = con.execute("SELECT produk, terjual, margin_persen FROM mart_produk WHERE catatan = 'kurang laku'").df()
    busy = con.execute("""SELECT jam, sum(transaksi) t FROM mart_jam GROUP BY jam ORDER BY t DESC LIMIT 3""").df()
    ringkasan = {
        "catatan": "DATA FIKTIF untuk demo Kemang Data (kemangdata.my.id). Kopi Senja adalah usaha karangan.",
        "diperbarui": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "periode": {"dari": start.isoformat(), "sampai": end.isoformat(), "hari": a.hari},
        "total": {"omzet": int(ch.omzet.sum()), "laba": int(ch.laba.sum()),
                  "margin_persen": round(float(ch.laba.sum() * 100 / ch.omzet.sum()), 1)},
        "per_channel": [dict(channel=r.channel, omzet=int(r.omzet), laba=int(r.laba), margin_persen=float(r.margin))
                        for r in ch.itertuples()],
        "produk_terlaris": [dict(produk=r.produk, terjual=int(r.terjual), omzet=int(r.omzet)) for r in top.itertuples()],
        "produk_kurang_laku": [dict(produk=r.produk, terjual=int(r.terjual), margin_persen=float(r.margin_persen))
                               for r in slow.itertuples()],
        "jam_ramai": [int(x) for x in busy.jam],
        "kualitas_data": {**{k: int(v) for k, v in nums.items()}, "baris_per_sumber": counts,
                          "cek": [dict(nama=n, lulus=bool(ok)) for n, ok, _ in checks]},
    }
    (a.out / "ringkasan.json").write_text(json.dumps(ringkasan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {start}..{end}: {nums['baris_mentah']} raw rows, {nums['baris_dobel_dibuang']} duplicates removed, "
          f"{nums['nama_produk_berbeda']} raw names -> {nums['produk_baku']} products -> {a.out}")


if __name__ == "__main__":
    main()
