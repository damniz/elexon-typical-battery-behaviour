"""Identifie les BM Units qui sont probablement des batteries.

Elexon ne publie pas de `fuelType = BATTERY` fiable. Le critère utile n'est pas
« l'unité peut importer et exporter » — toute centrale thermique consomme
quelques MW de services auxiliaires — mais **le rapport entre les deux** :

    une batterie importe à peu près autant qu'elle exporte, soit
    |demandCapacity| / generationCapacity proche de 1.

Une CCGT de 950 MW qui consomme 10 MW donne un rapport de 0,01. Une batterie
donne un rapport entre 0,7 et 1,3.

Restent alors deux familles à écarter :
  * le pompage-turbinage, exclu nommément (Dinorwig, Ffestiniog, Foyers, Cruachan) ;
  * les unités d'agrégation des fournisseurs, préfixées `2__`.

Usage :
    python src/discover_batteries.py
    python src/discover_batteries.py --min-mw 20 --top 40
    python src/discover_batteries.py --fuel-types      # que publie vraiment Elexon ?
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import elexon

DATA = Path(__file__).resolve().parent.parent / "data"

PUMPED_STORAGE_PREFIXES = ("DINO", "FFES", "FOYE", "CRUA")
SUPPLIER_PREFIXES = ("2__",)

# Rapport import/export admissible pour un actif de stockage.
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
        # Deux CHP biomasse passent le filtre de rapport : Elexon les etiquette,
        # autant s'en servir.
        & df["fuelType"].ne("BIOMASS")
    )

    candidates = df[keep].copy()
    # Le plus proche de 1 en premier, à capacité comparable.
    candidates["ratioGap"] = (candidates["importExportRatio"] - 1).abs()
    return candidates.sort_values(["exportMW", "ratioGap"],
                                  ascending=[False, True]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-mw", type=float, default=10.0)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--fuel-types", action="store_true",
                        help="afficher les valeurs de fuelType publiees, puis quitter")
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

    print(f"{len(candidates)} candidats (export >= {args.min_mw:g} MW, "
          f"rapport import/export entre {RATIO_MIN} et {RATIO_MAX})")
    print(f"Liste complete : {output}\n")
    with pd.option_context("display.width", 220, "display.max_colwidth", 38):
        print(candidates[columns].head(args.top).to_string(index=False))

    if not candidates.empty:
        best = candidates.iloc[0]
        print("\nEtape suivante, par exemple :")
        print(f"  python src/fetch.py --bmu {best['elexonBmUnit']} "
              f"--day AAAA-MM-JJ --months 12")


if __name__ == "__main__":
    main()
