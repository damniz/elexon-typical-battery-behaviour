"""Download everything the figure needs and cache it under data/.

Two datasets:
  * the showcase day - the battery's power profile, its acceptances, and the
    imbalance price;
  * the long history - the same, over twelve months, for the typical profile.

Usage:
    python src/fetch.py --bmu E_STALB-1 --day 2026-07-25 --months 12
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import elexon

DATA = Path(__file__).resolve().parent.parent / "data"
TZ = ZoneInfo("Europe/London")


def _utc(day: date, hour: int = 0) -> datetime:
    """Local British midnight, expressed in UTC for the API."""
    local = datetime(day.year, day.month, day.day, hour, tzinfo=TZ)
    return local.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bmu", required=True,
                        help="BM Unit identifier, e.g. E_STALB-1")
    parser.add_argument("--day", required=True,
                        help="showcase day, YYYY-MM-DD")
    parser.add_argument("--months", type=int, default=12,
                        help="months of history to download (0 to skip it)")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    day = date.fromisoformat(args.day)
    slug = args.bmu.replace("/", "-")

    print(f"Showcase day {day} for {args.bmu} ...")
    day_profile = elexon.physical(args.bmu, _utc(day), _utc(day + timedelta(days=1)))
    if day_profile.empty:
        hint = ""
        if "XXX" in args.bmu.upper():
            hint = ("\n\nThat identifier looks like the placeholder from the README. "
                    "Run this first:\n  python src/discover_batteries.py --min-mw 20")
        raise SystemExit(
            f"No PN data for {args.bmu} on {day}. "
            f"Check the identifier or pick another date.{hint}"
        )
    day_profile.to_csv(DATA / f"pn_day_{slug}_{day}.csv", index=False)
    print(f"  {len(day_profile)} points")

    print(f"Bid-offer acceptances {day} ...")
    day_boalf = elexon.acceptances_for_unit(
        args.bmu, _utc(day), _utc(day + timedelta(days=1)))
    day_boalf.to_csv(DATA / f"boalf_day_{slug}_{day}.csv", index=False)
    print(f"  {len(day_boalf)} acceptances")

    print(f"Imbalance prices {day} ...")
    prices = elexon.system_prices(day)
    prices.to_csv(DATA / f"prices_{day}.csv", index=False)
    print(f"  {len(prices)} settlement periods")

    if args.months > 0:
        end = _utc(day + timedelta(days=1))
        start = end - timedelta(days=30 * args.months)
        print(f"History from {start:%Y-%m-%d} to {end:%Y-%m-%d} "
              f"(seven-day chunks, expect a few minutes) ...")
        history = elexon.physical(args.bmu, start, end)
        history.to_csv(DATA / f"pn_history_{slug}.csv", index=False)
        print(f"  {len(history)} PN points")

        history_boalf = elexon.acceptances_for_unit(args.bmu, start, end)
        history_boalf.to_csv(DATA / f"boalf_history_{slug}.csv", index=False)
        print(f"  {len(history_boalf)} acceptances")

    print("\nDone. Next step:")
    print(f"  python src/make_figure.py --bmu {args.bmu} --day {day} --stat mean")


if __name__ == "__main__":
    main()
