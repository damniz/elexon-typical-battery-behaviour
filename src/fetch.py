"""Telecharge les donnees necessaires a la figure et les met en cache dans data/.

Deux jeux de donnees :
  * la journee vitrine  -> profil de puissance de la batterie + prix de desequilibre
  * l'historique long   -> meme profil sur 12 mois, pour le comportement typique

Usage :
    python src/fetch.py --bmu T_XXXXX-1 --day 2026-06-18 --months 12
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import elexon

DATA = Path(__file__).resolve().parent.parent / "data"


TZ = ZoneInfo("Europe/London")


def _utc(day: date, hour: int = 0) -> datetime:
    """Minuit heure locale britannique, exprimé en UTC pour l'API."""
    local = datetime(day.year, day.month, day.day, hour, tzinfo=TZ)
    return local.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bmu", required=True,
                        help="identifiant BM Unit, par ex. T_XXXXX-1")
    parser.add_argument("--day", required=True,
                        help="journee vitrine, format YYYY-MM-DD")
    parser.add_argument("--months", type=int, default=12,
                        help="profondeur d'historique en mois (0 pour ne pas le telecharger)")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    day = date.fromisoformat(args.day)
    slug = args.bmu.replace("/", "-")

    print(f"Journee vitrine {day} pour {args.bmu} ...")
    day_profile = elexon.physical(args.bmu, _utc(day), _utc(day + timedelta(days=1)))
    if day_profile.empty:
        hint = ""
        if set(args.bmu.upper()) <= set("TVX_-0123456789") and "XXX" in args.bmu.upper():
            hint = ("\n\nL'identifiant fourni ressemble a l'exemple generique du README. "
                    "Lancer d'abord :\n  python src/discover_batteries.py --min-mw 50")
        raise SystemExit(
            f"Aucune donnee PN pour {args.bmu} le {day}. "
            f"Verifier l'identifiant ou choisir une autre date.{hint}"
        )
    day_profile.to_csv(DATA / f"pn_day_{slug}_{day}.csv", index=False)
    print(f"  {len(day_profile)} points")

    print(f"Acceptations d'offres {day} ...")
    day_boalf = elexon.acceptances_for_unit(
        args.bmu, _utc(day), _utc(day + timedelta(days=1)))
    day_boalf.to_csv(DATA / f"boalf_day_{slug}_{day}.csv", index=False)
    print(f"  {len(day_boalf)} acceptations")

    print(f"Prix de desequilibre {day} ...")
    prices = elexon.system_prices(day)
    prices.to_csv(DATA / f"prices_{day}.csv", index=False)
    print(f"  {len(prices)} periodes de reglement")

    if args.months > 0:
        end = _utc(day + timedelta(days=1))
        start = end - timedelta(days=30 * args.months)
        print(f"Historique du {start:%Y-%m-%d} au {end:%Y-%m-%d} "
              f"(par tranches de 7 jours, comptez quelques minutes) ...")
        history = elexon.physical(args.bmu, start, end)
        history.to_csv(DATA / f"pn_history_{slug}.csv", index=False)
        print(f"  {len(history)} points de PN")

        history_boalf = elexon.acceptances_for_unit(args.bmu, start, end)
        history_boalf.to_csv(DATA / f"boalf_history_{slug}.csv", index=False)
        print(f"  {len(history_boalf)} acceptations")

    print("\nTermine. Etape suivante :")
    print(f"  python src/make_figure.py --bmu {args.bmu} --day {day}")


if __name__ == "__main__":
    main()
