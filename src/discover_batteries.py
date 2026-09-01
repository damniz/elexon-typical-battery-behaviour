"""Find the BM Units that are most likely batteries.

Elexon does not publish a reliable `fuelType = BATTERY`. The useful signal is
not "the unit can both import and export" - every thermal plant draws a few MW
of station load - but **the ratio between the two**:

    a battery imports about as much as it exports, so
    |demandCapacity| / generationCapacity is close to 1.

A 950 MW CCGT drawing 10 MW gives a ratio of 0.01. A battery gives 0.7 to 1.3.

Two families still slip through and are removed by name:
  * pumped storage (Dinorwig, Ffestiniog, Foyers, Cruachan);
  * supplier aggregation units, prefixed `2__`.

Usage:
    python src/discover_batteries.py
    python src/discover_batteries.py --min-mw 20 --top 40
    python src/discover_batteries.py --fuel-types     # what does Elexon actually publish?
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import elexon

DATA = Path(__file__).resolve().parent.parent / "data"

PUMPED_STORAGE_PREFIXES = ("DINO", "FFES", "FOYE", "CRUA")
SUPPLIER_PREFIXES = ("2__",)

# Import/export ratio a storage asset is expected to fall within.
RATIO_MIN, RATIO_MAX = 0.55, 1.8


def load_units() -> pd.DataFrame:
    units = elexon.bm_units()
    for column in ("demandCapacity", "generationCapacity"):
        units[column] = pd.to_numeric(units[column], errors="coerce")
    return units


def find_batteries(units: pd.DataFrame, min_mw: float = 10.0) -> pd.DataFrame:
    df = units.copy()
    df["exportMW"] = df["generationCapacity"].abs()
    df["importMW"] = df["demandCapacity"].abs()
    df["importExportRatio"] = (df["importMW"] / df["exportMW"]).round(2)

    identifier = df["elexonBmUnit"].astype(str).str.upper()
    national = df["nationalGridBmUnit"].astype(str).str.upper()

    keep = (
        df["exportMW"].ge(min_mw)
        & df["importExportRatio"].between(RATIO_MIN, RATIO_MAX)
        & df["interconnectorId"].isna()
        & ~identifier.str.startswith(SUPPLIER_PREFIXES)
        & ~national.str.startswith(PUMPED_STORAGE_PREFIXES)
        # Two biomass CHP plants pass the ratio test; Elexon labels them, so
        # we may as well use that.
        & df["fuelType"].ne("BIOMASS")
    )

    candidates = df[keep].copy()
    # Closest to a 1:1 ratio first, at comparable capacity.
    candidates["ratioGap"] = (candidates["importExportRatio"] - 1).abs()
    return candidates.sort_values(["exportMW", "ratioGap"],
                                  ascending=[False, True]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-mw", type=float, default=10.0,
                        help="minimum export capacity to keep (MW)")
    parser.add_argument("--top", type=int, default=30,
                        help="number of rows printed")
    parser.add_argument("--fuel-types", action="store_true",
                        help="print the fuelType values Elexon publishes, then exit")
    args = parser.parse_args()

    units = load_units()

    if args.fuel_types:
        print(units["fuelType"].value_counts(dropna=False).to_string())
        return

    candidates = find_batteries(units, args.min_mw)

    DATA.mkdir(exist_ok=True)
    output = DATA / "battery_bmus.csv"
    candidates.to_csv(output, index=False)

    columns = ["elexonBmUnit", "bmUnitName", "leadPartyName",
               "exportMW", "importMW", "importExportRatio", "fuelType"]
    columns = [c for c in columns if c in candidates.columns]

    print(f"{len(candidates)} candidates (export >= {args.min_mw:g} MW, "
          f"import/export ratio between {RATIO_MIN} and {RATIO_MAX})")
    print(f"Full list written to {output}\n")
    with pd.option_context("display.width", 220, "display.max_colwidth", 38):
        print(candidates[columns].head(args.top).to_string(index=False))

    if not candidates.empty:
        best = candidates.iloc[0]
        print("\nNext step, for instance:")
        print(f"  python src/screen_units.py --units 25 --days 14")
        print(f"  python src/fetch.py --bmu {best['elexonBmUnit']} "
              f"--day YYYY-MM-DD --months 12")


if __name__ == "__main__":
    main()
