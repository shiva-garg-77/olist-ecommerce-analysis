"""
Step 3 runner: execute every @name-tagged query in sql/02_analysis_queries.sql
against the SQLite warehouse and export each result set to
reports/sql_results/<name>.csv.

Run:  python -m src.sql_analysis
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import DB_PATH, REPORTS_DIR, SQL_DIR

RESULTS_DIR = REPORTS_DIR / "sql_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

QUERY_FILE = SQL_DIR / "02_analysis_queries.sql"
NAME_PATTERN = re.compile(r"^--\s*@name:\s*([a-zA-Z0-9_]+)\s*$", re.MULTILINE)


def parse_queries(sql_text: str) -> dict[str, str]:
    """Split the .sql file into {name: statement} using the @name markers."""
    parts = NAME_PATTERN.split(sql_text)
    # parts = [preamble, name1, body1, name2, body2, ...]
    queries: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        name = parts[i].strip()
        body = parts[i + 1].strip()
        queries[name] = body
    return queries


def run_all(verbose: bool = True) -> dict[str, pd.DataFrame]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found - run `python -m src.etl` first.")

    queries = parse_queries(QUERY_FILE.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB_PATH)
    results: dict[str, pd.DataFrame] = {}

    for name, sql in queries.items():
        try:
            df = pd.read_sql_query(sql, con)
        except Exception as exc:  # surface the failing query, keep going
            print(f"  [FAIL] {name}: {exc}")
            continue
        results[name] = df
        df.to_csv(RESULTS_DIR / f"{name}.csv", index=False)
        if verbose:
            print(f"\n{'=' * 78}\n{name}  ({len(df)} rows)\n{'=' * 78}")
            print(df.head(12).to_string(index=False))

    con.close()
    print(f"\n{len(results)}/{len(queries)} queries executed -> {RESULTS_DIR}")
    return results


if __name__ == "__main__":
    run_all()
