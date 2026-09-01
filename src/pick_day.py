"""Find a day worth plotting.

A figure only reads if the price moved that day. This script walks back over
the last N days, measures how dispersed the intraday imbalance price was, and
ranks the days.

Two measures, because they say different things:
  * `spread`  = max - min, sensitive to a single isolated spike;
  * `p90_p10` = interdecile range, which describes a genuinely eventful day.

Usage:
    python src/pick_day.py --days 90
    python src/pick_day.py --days 180 --top 15 --by negativePeriods
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd

import elexon


def scan(days: int) -> pd.DataFrame:
    today = date.today()
    rows = []
    for offset in range(2, days + 2):          # yesterday is not settled yet
        day = today - timedelta(days=offset)
        try:
            prices = elexon.system_prices(day)
        except RuntimeError:
            continue
        if prices.empty:
            continue
        values = pd.to_numeric(prices["systemSellPrice"], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append({
            "day": day,
            "min": round(values.min(), 1),
            "max": round(values.max(), 1),
            "spread": round(values.max() - values.min(), 1),
            "p90_p10": round(values.quantile(0.9) - values.quantile(0.1), 1),
            "negativePeriods": int((values < 0).sum()),
        })
        print(f"  {day} ...", end="\r")
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--by", choices=["spread", "p90_p10", "negativePeriods"],
                        default="p90_p10")
    args = parser.parse_args()

    print(f"Scanning the last {args.days} days (one request per day)...")
    table = scan(args.days)
    if table.empty:
        raise SystemExit("No price data retrieved.")

    ranked = table.sort_values(args.by, ascending=False).head(args.top)
    print(f"\nMost eventful days, ranked by {args.by}:\n")
    print(ranked.to_string(index=False))

    best = ranked.iloc[0]
    print("\nNext step:")
    print(f"  python src/fetch.py --bmu <BM Unit> --day {best['day']} --months 12")


if __name__ == "__main__":
    main()
