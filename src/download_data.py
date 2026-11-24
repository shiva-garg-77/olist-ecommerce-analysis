"""
Download the 9 raw Olist CSVs into data/raw/.

Pulls from a public mirror of the Kaggle "Brazilian E-Commerce Public Dataset by
Olist" (same files, same row counts). If you already downloaded the Kaggle zip,
just drop the CSVs into data/raw/ and skip this script.

Run:  python -m src.download_data
"""

from __future__ import annotations

import sys
import urllib.request

from src.config import DATA_RAW, RAW_FILES

MIRROR = "https://huggingface.co/datasets/bulutttt/olist-raw-data/resolve/main/"
EXPECTED_ROWS = {
    "orders": 99441,
    "customers": 99441,
    "order_items": 112650,
    "payments": 103886,
    "reviews": 99224,
    "products": 32951,
    "sellers": 3095,
    "geolocation": 1000163,
    "category_translation": 71,
}


def main(force: bool = False) -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    for name, filename in RAW_FILES.items():
        target = DATA_RAW / filename
        if target.exists() and not force:
            print(f"  skip  {filename} (already present)")
            continue
        url = MIRROR + filename
        print(f"  get   {filename} ...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, target)
            print(f"ok ({target.stat().st_size / 1e6:.1f} MB)")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")
            sys.exit(1)

    print("\nverifying row counts ...")
    ok = True
    for name, filename in RAW_FILES.items():
        with open(DATA_RAW / filename, encoding="utf-8") as f:
            rows = sum(1 for _ in f) - 1
        expected = EXPECTED_ROWS[name]
        flag = "ok " if rows == expected else "!! "
        if rows != expected:
            ok = False
        print(f"  {flag}{filename:45s} {rows:>9,} rows (expected {expected:,})")
    print("\nall files match the reference dataset" if ok else "\nrow counts differ - check the download")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
