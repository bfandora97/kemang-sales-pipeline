"""Reference data: product master (price, cost), name aliases per source, channel commission."""
from pathlib import Path

import pandas as pd

CONFIG = Path(__file__).resolve().parent.parent / "config"


def load_produk():
    return pd.read_csv(CONFIG / "produk.csv")


def load_alias():
    return pd.read_csv(CONFIG / "alias.csv")


def load_channel():
    return pd.read_csv(CONFIG / "channel.csv")
