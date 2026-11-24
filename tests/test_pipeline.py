"""End-to-end tests: a clean week passes, and a broken export is stopped by the quality gate."""
import json
from datetime import date

import pandas as pd
import pytest

from kopisenja.generate import generate_day
from kopisenja.run import main

END = date(2026, 11, 24)


def run(tmp_path, hari=7):
    main(["--sampai", END.isoformat(), "--hari", str(hari), "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "out")])
    return json.loads((tmp_path / "out" / "ringkasan.json").read_text(encoding="utf-8"))


def test_clean_week_passes_all_checks(tmp_path):
    r = run(tmp_path)
    assert all(c["lulus"] for c in r["kualitas_data"]["cek"])
    assert r["kualitas_data"]["produk_baku"] == 10
    assert r["kualitas_data"]["baris_dobel_dibuang"] > 0          # duplicates exist in raw and were removed
    assert {c["channel"] for c in r["per_channel"]} == {"Outlet Kemang", "Outlet Tebet", "GoFood/GrabFood", "Shopee"}


def test_delivery_apps_have_lower_margin_than_outlets(tmp_path):
    m = {c["channel"]: c["margin_persen"] for c in run(tmp_path, 30)["per_channel"]}
    assert m["GoFood/GrabFood"] < m["Shopee"] < m["Outlet Kemang"]


def test_generator_is_deterministic(tmp_path):
    a = generate_day(END, tmp_path / "a") / "kasir_kemang.csv"
    b = generate_day(END, tmp_path / "b") / "kasir_kemang.csv"
    assert a.read_bytes() == b.read_bytes()


def test_unknown_product_name_stops_the_pipeline(tmp_path):
    folder = generate_day(END, tmp_path / "raw")
    f = folder / "gofood.csv"
    df = pd.read_csv(f, dtype=str)
    df.loc[0, "Item Name"] = "Es Kopi Pandan Baru"                # new menu item not in config/alias.csv
    df.to_csv(f, index=False)
    with pytest.raises(SystemExit):
        main(["--sampai", END.isoformat(), "--hari", "1", "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "out")])
    assert not (tmp_path / "out" / "ringkasan.json").exists()      # bad data never reaches the report
