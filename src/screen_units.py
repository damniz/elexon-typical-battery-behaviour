"""Rank candidate batteries by how much they actually do in the data.

A battery can sit in the reference list and leave nothing readable behind: a
physical notification flat at zero and no acceptances at all. Thornton Battery
is one such case - 200 MW installed, nothing in the operational data. Picking
an asset on installed capacity alone therefore wastes a full round trip.

This script samples a recent window for each candidate and measures:
  * `pnActivity`  - share of physical notification points that are non-zero;
  * `pnPeakMW`    - amplitude reached in the PN;
  * `acceptances` - number of bid-offer acceptances over the window;
  * `boalfPeakMW` - amplitude reached through acceptances.

A good candidate has either a live PN or plenty of acceptances.

Usage:
    python src/screen_units.py --units 25 --days 14
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import elexon

DATA = Path(__file__).resolve().parent.parent / "data"


def screen(bm_unit: str, start: datetime, end: datetime) -> dict:
    row = {"elexonBmUnit": bm_unit, "pnActivity": 0.0, "pnPeakMW": 0.0,
           "acceptances": 0, "boalfPeakMW": 0.0}

    pn = elexon.physical(bm_unit, start, end)
    if not pn.empty:
        levels = pd.concat([pn["levelFrom"], pn["levelTo"]]).astype(float)
        row["pnActivity"] = round(float((levels.abs() > 0.5).mean()), 3)
        row["pnPeakMW"] = round(float(levels.abs().max()), 1)

    boalf = elexon.acceptances_for_unit(bm_unit, start, end)
    if not boalf.empty:
        levels = pd.concat([boalf["levelFrom"], boalf["levelTo"]]).astype(float)
        row["acceptances"] = int(len(boalf))
        row["boalfPeakMW"] = round(float(levels.abs().max()), 1)

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, default=25,
                        help="how many candidates to test, largest capacity first")
    parser.add_argument("--days", type=int, default=14,
                        help="length of the sample window")
    args = parser.parse_args()

    candidates = pd.read_csv(DATA / "battery_bmus.csv")
    shortlist = candidates.head(args.units)

    end = datetime.combine(date.today() - timedelta(days=3),
                           datetime.min.time(), tzinfo=timezone.utc)
    start = end - timedelta(days=args.days)
    print(f"Sampling {start:%Y-%m-%d} to {end:%Y-%m-%d}, "
          f"{len(shortlist)} units (two requests each)\n")

    rows = []
    for position, unit in enumerate(shortlist.itertuples(), start=1):
        print(f"  [{position}/{len(shortlist)}] {unit.elexonBmUnit} ...", end="\r")
        try:
            row = screen(unit.elexonBmUnit, start, end)
        except RuntimeError as exc:
            print(f"  {unit.elexonBmUnit}: failed ({exc})")
            continue
        row["bmUnitName"] = unit.bmUnitName
        row["exportMW"] = unit.exportMW
        rows.append(row)

    table = pd.DataFrame(rows)
    if table.empty:
        raise SystemExit("No usable unit found.")

    table["score"] = table["pnActivity"] * 100 + table["acceptances"]
    table = table.sort_values("score", ascending=False).reset_index(drop=True)
    table.to_csv(DATA / "screening.csv", index=False)

    columns = ["elexonBmUnit", "bmUnitName", "exportMW",
               "pnActivity", "pnPeakMW", "acceptances", "boalfPeakMW"]
    with pd.option_context("display.width", 220, "display.max_colwidth", 34):
        print("\n" + table[columns].to_string(index=False))

    best = table.iloc[0]
    print(f"\nBest candidate: {best['elexonBmUnit']} ({best['bmUnitName']})")
    print("Next step:")
    print(f"  python src/fetch.py --bmu {best['elexonBmUnit']} "
          f"--day YYYY-MM-DD --months 12")


if __name__ == "__main__":
    main()
