"""Trouve une journée intéressante à représenter.

Une figure n'est lisible que si le prix a bougé ce jour-là. Le script parcourt
les N derniers jours, mesure la dispersion intra-journalière du prix de
déséquilibre, et classe les journées.

Deux mesures, parce qu'elles ne disent pas la même chose :
  * `spread`  = max - min, sensible à un seul pic isolé ;
  * `p90_p10` = écart interdécile, qui décrit une journée franchement agitée.

Usage :
    python src/pick_day.py --days 90
    python src/pick_day.py --days 180 --top 15
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import pandas as pd

import elexon


def scan(days: int) -> pd.DataFrame:
    today = date.today()
    rows = []
    for offset in range(2, days + 2):          # J-1 n'est pas encore consolide
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

    print(f"Balayage des {args.days} derniers jours (une requete par jour)...")
    table = scan(args.days)
    if table.empty:
        raise SystemExit("Aucune donnee de prix recuperee.")

    ranked = table.sort_values(args.by, ascending=False).head(args.top)
    print(f"\nJournees les plus agitees, classees par {args.by} :\n")
    print(ranked.to_string(index=False))

    best = ranked.iloc[0]
    print("\nEtape suivante :")
    print(f"  python src/fetch.py --bmu T_BLWNB-1 --day {best['day']} --months 12")


if __name__ == "__main__":
    main()
