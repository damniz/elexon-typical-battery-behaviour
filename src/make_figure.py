"""Build the figure: the same battery seen at two horizons.

Three stacked panels:
  1. one real day  - the battery's power (discharging above zero, charging below);
  2. the same day  - the system imbalance price;
  3. twelve months - the typical profile by time of day, with the interquartile range.

Two different scales never share an axis: the price gets its own panel rather
than a second y-axis laid over the power. A dual axis lets the reader pick
whichever correlation they want by rescaling; two aligned panels say the same
thing honestly.

Usage:
    python src/make_figure.py --bmu E_STALB-1 --day 2026-07-25 --stat mean
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGURES = ROOT / "figures"

TZ = "Europe/London"

# Validated diverging palette (blue <-> red, grey midpoint) on a light surface.
SURFACE = "#fcfcfb"
DISCHARGE = "#e34948"   # warm pole: the battery exports
CHARGE = "#2a78d6"      # cool pole: the battery imports
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

LABELS = {
    "en": {
        "title": "The same battery, two horizons",
        "day": "One day — {date:%d %B %Y}, half-hourly",
        "price": "System imbalance price, same day",
        "typical": "Twelve months — {stat} profile by time of day",
        "stat_median": "median",
        "stat_mean": "mean",
        "discharge": "discharging",
        "charge": "charging",
        "negative": "negative prices",
        "band": "25–75% range",
        "power_axis": "MW",
        "price_axis": "GBP / MWh",
        "source": "Data: Elexon Insights (BMRS), data.elexon.co.uk",
        "source_boalf": "  ·  profile = physical notification + bid-offer acceptances",
        "written": "Figure written to",
    },
    "fr": {
        "title": "La même batterie, deux horizons",
        "day": "Une journée — {date:%d/%m/%Y}, pas demi-horaire",
        "price": "Le prix de déséquilibre du système, le même jour",
        "typical": "Douze mois — profil {stat} par heure de la journée",
        "stat_median": "médian",
        "stat_mean": "moyen",
        "discharge": "décharge",
        "charge": "charge",
        "negative": "prix négatifs",
        "band": "quartiles 25-75 %",
        "power_axis": "MW",
        "price_axis": "GBP / MWh",
        "source": "Données : Elexon Insights (BMRS), data.elexon.co.uk",
        "source_boalf": "  ·  profil = notification physique + acceptations d'offres",
        "written": "Figure écrite :",
    },
}

L = LABELS["en"]


def _style() -> None:
    mpl.rcParams.update({
        "font.family": ["DejaVu Sans"],
        "font.size": 15,
        "axes.titlesize": 17,
        "axes.labelsize": 14,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
    })


def _points(pn: pd.DataFrame) -> pd.Series:
    """Turn PN segments (levelFrom -> levelTo) into a series of points."""
    starts = pn[["timeFrom", "levelFrom"]].rename(
        columns={"timeFrom": "time", "levelFrom": "mw"})
    ends = pn[["timeTo", "levelTo"]].rename(
        columns={"timeTo": "time", "levelTo": "mw"})
    points = pd.concat([starts, ends], ignore_index=True)
    points["time"] = pd.to_datetime(points["time"], utc=True).dt.tz_convert(TZ)
    points["mw"] = pd.to_numeric(points["mw"], errors="coerce")
    points = points.dropna().drop_duplicates(subset="time", keep="last")
    return points.set_index("time")["mw"].sort_index()


def _acceptance_overlay(boalf: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    """Levels imposed by acceptances, resampled onto the requested grid."""
    overlay = pd.Series(np.nan, index=index)
    if boalf.empty:
        return overlay

    frame = boalf.copy()
    for column in ("timeFrom", "timeTo"):
        frame[column] = pd.to_datetime(frame[column], utc=True).dt.tz_convert(TZ)
    if "acceptanceTime" in frame.columns:
        frame["acceptanceTime"] = pd.to_datetime(frame["acceptanceTime"], utc=True)
        frame = frame.sort_values("acceptanceTime")

    # Later acceptances override earlier ones.
    for row in frame.itertuples():
        mask = (index >= row.timeFrom) & (index <= row.timeTo)
        if not mask.any():
            continue
        span = (row.timeTo - row.timeFrom).total_seconds()
        if span <= 0:
            overlay[mask] = float(row.levelFrom)
            continue
        elapsed = (index[mask] - row.timeFrom).total_seconds() / span
        overlay[mask] = float(row.levelFrom) + elapsed * (
            float(row.levelTo) - float(row.levelFrom))
    return overlay


def effective_profile(pn: pd.DataFrame, boalf: pd.DataFrame,
                      index: pd.DatetimeIndex) -> tuple[pd.Series, bool]:
    """What the battery actually does: the PN, overridden by acceptances."""
    points = _points(pn)
    if points.empty:
        base = pd.Series(0.0, index=index)
    else:
        base = (points.reindex(points.index.union(index))
                      .interpolate(method="time")
                      .reindex(index)
                      .fillna(0.0))
    overlay = _acceptance_overlay(boalf, index)
    return overlay.fillna(base), bool(overlay.notna().any())


def negative_price_spans(prices: pd.DataFrame) -> list[tuple]:
    """Intervals where the imbalance price drops below zero."""
    times = pd.to_datetime(prices["startTime"], utc=True).dt.tz_convert(TZ)
    values = pd.to_numeric(prices["systemSellPrice"], errors="coerce")
    spans, opened = [], None
    for moment, value in zip(times, values):
        if value < 0 and opened is None:
            opened = moment
        elif value >= 0 and opened is not None:
            spans.append((opened, moment))
            opened = None
    if opened is not None:
        spans.append((opened, times.iloc[-1] + pd.Timedelta(minutes=30)))
    return spans


def shade_spans(ax, spans: list[tuple], label: bool = False) -> None:
    """Same shading on both day panels, so the two read together."""
    for index, (begin, finish) in enumerate(spans):
        ax.axvspan(begin, finish, color=MUTED, alpha=0.13, linewidth=0, zorder=0)
        if label and index == 0:
            ax.annotate(L["negative"], xy=(finish, ax.get_ylim()[1]),
                        xytext=(6, -18), textcoords="offset points",
                        fontsize=13, color=INK_SECONDARY)


def _tidy(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", visible=False)
    ax.tick_params(colors=MUTED, length=0)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(INK_SECONDARY)


def panel_day(ax, power: pd.Series) -> None:
    ax.fill_between(power.index, 0, power.values, where=power.values >= 0,
                    color=DISCHARGE, alpha=0.85, interpolate=True, linewidth=0)
    ax.fill_between(power.index, 0, power.values, where=power.values <= 0,
                    color=CHARGE, alpha=0.85, interpolate=True, linewidth=0)
    ax.plot(power.index, power.values, color=SURFACE, linewidth=2)
    ax.axhline(0, color=AXIS, linewidth=1.2)

    ax.set_ylabel(L["power_axis"], color=INK_SECONDARY)
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%H:%M", tz=power.index.tz))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(interval=4))

    ax.annotate(L["discharge"], xy=(0.012, 0.90), xycoords="axes fraction",
                color=DISCHARGE, fontsize=15, fontweight="bold")
    ax.annotate(L["charge"], xy=(0.012, 0.06), xycoords="axes fraction",
                color=CHARGE, fontsize=15, fontweight="bold")

    # Symmetric limits: on a diverging encoding the eye compares the two sides.
    reach = float(max(abs(power.max()), abs(power.min()))) * 1.18
    ax.set_ylim(-reach, reach)
    ax.set_xlim(power.index.min(), power.index.max())
    _tidy(ax)


def panel_price(ax, prices: pd.DataFrame) -> None:
    times = pd.to_datetime(prices["startTime"], utc=True).dt.tz_convert(TZ)
    values = pd.to_numeric(prices["systemSellPrice"], errors="coerce")
    ax.step(times, values, where="post", color=INK, linewidth=2)
    ax.axhline(0, color=AXIS, linewidth=1.2)
    ax.set_ylabel(L["price_axis"], color=INK_SECONDARY)
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%H:%M", tz=times.dt.tz))
    ax.xaxis.set_major_locator(mpl.dates.HourLocator(interval=4))
    _tidy(ax)


def panel_typical(ax, power: pd.Series, stat: str = "median") -> None:
    half_hourly = power.resample("30min").mean().dropna()
    minutes = half_hourly.index.hour * 60 + half_hourly.index.minute
    grouped = half_hourly.groupby(minutes)

    central = grouped.median() if stat == "median" else grouped.mean()
    hours = [m / 60 for m in central.index]
    middle = central.values
    low = grouped.quantile(0.25).values
    high = grouped.quantile(0.75).values

    ax.fill_between(hours, low, high, color=MUTED, alpha=0.22, linewidth=0)
    ax.fill_between(hours, 0, middle, where=middle >= 0,
                    color=DISCHARGE, alpha=0.85, interpolate=True, linewidth=0)
    ax.fill_between(hours, 0, middle, where=middle <= 0,
                    color=CHARGE, alpha=0.85, interpolate=True, linewidth=0)
    ax.plot(hours, middle, color=SURFACE, linewidth=2)
    ax.axhline(0, color=AXIS, linewidth=1.2)

    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 4)])
    ax.set_ylabel(L["power_axis"], color=INK_SECONDARY)
    ax.legend(
        handles=[Line2D([0], [0], color=MUTED, alpha=0.4, linewidth=10,
                        label=L["band"])],
        loc="upper left", frameon=False, fontsize=13, labelcolor=INK_SECONDARY)
    _tidy(ax)


def main() -> None:
    global L

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bmu", required=True)
    parser.add_argument("--day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--lang", choices=["en", "fr"], default="en",
                        help="language of the figure labels")
    parser.add_argument("--stat", choices=["median", "mean"], default="median",
                        help="statistic for the long panel: median (robust) or "
                             "mean (reflects net energy moved)")
    parser.add_argument("--name", default=None,
                        help="readable asset name for the subtitle")
    args = parser.parse_args()

    L = LABELS[args.lang]

    day = date.fromisoformat(args.day)
    slug = args.bmu.replace("/", "-")
    label = args.name or args.bmu

    def _read(path: Path) -> pd.DataFrame:
        return pd.read_csv(path) if path.exists() else pd.DataFrame()

    day_pn = pd.read_csv(DATA / f"pn_day_{slug}_{day}.csv")
    day_boalf = _read(DATA / f"boalf_day_{slug}_{day}.csv")
    prices = pd.read_csv(DATA / f"prices_{day}.csv")
    history_path = DATA / f"pn_history_{slug}.csv"
    history_boalf = _read(DATA / f"boalf_history_{slug}.csv")

    day_start = pd.Timestamp(f"{day} 00:00", tz=TZ)
    day_index = pd.date_range(day_start, day_start + pd.Timedelta(days=1),
                              freq="1min", tz=TZ)
    day_power, day_had_acceptances = effective_profile(day_pn, day_boalf, day_index)

    _style()
    has_history = history_path.exists()
    rows = 3 if has_history else 2
    ratios = [3, 2, 3][:rows]

    fig, axes = plt.subplots(rows, 1, figsize=(10, 10), dpi=120,
                             gridspec_kw={"height_ratios": ratios, "hspace": 0.55})

    spans = negative_price_spans(prices)

    panel_day(axes[0], day_power)
    shade_spans(axes[0], spans, label=True)
    axes[0].set_title(L["day"].format(date=day),
                      loc="left", color=INK, fontweight="bold", pad=12)

    panel_price(axes[1], prices)
    shade_spans(axes[1], spans)
    axes[1].set_title(L["price"], loc="left", color=INK, fontweight="bold", pad=12)
    # Same time window as the panel above, so the two read together.
    axes[1].set_xlim(axes[0].get_xlim())

    if has_history:
        history_pn = pd.read_csv(history_path)
        span = _points(history_pn)
        history_index = pd.date_range(span.index.min().floor("D"),
                                      span.index.max().ceil("D"),
                                      freq="5min", tz=TZ)
        history_power, _ = effective_profile(history_pn, history_boalf, history_index)
        panel_typical(axes[2], history_power, stat=args.stat)
        wording = L["stat_median"] if args.stat == "median" else L["stat_mean"]
        axes[2].set_title(L["typical"].format(stat=wording),
                          loc="left", color=INK, fontweight="bold", pad=12)

    fig.suptitle(L["title"], x=0.055, y=0.985, ha="left", fontsize=22,
                 fontweight="bold", color=INK)
    fig.text(0.055, 0.938, label, ha="left", fontsize=15, color=INK_SECONDARY)

    source = L["source"]
    if day_had_acceptances:
        source += L["source_boalf"]
    fig.text(0.055, 0.012, source, fontsize=12, color=MUTED)

    fig.subplots_adjust(top=0.87, bottom=0.06, left=0.11, right=0.97)

    FIGURES.mkdir(exist_ok=True)
    output = FIGURES / f"two_horizons_{slug}_{day}.png"
    fig.savefig(output)
    print(f"{L['written']} {output}")


if __name__ == "__main__":
    main()
