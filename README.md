# elexon-typical-battery-behaviour

How a GB grid battery actually behaves, reconstructed from the public
[Elexon Insights (BMRS)](https://developer.data.elexon.co.uk/) data.

The API is public and needs no key. The data is covered by the
[Elexon BMRS API licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-use-bmrs-api/),
which requires attribution.

## What this produces

A square 1200 × 1200 figure with three panels:

1. **One day** — a named battery's power profile at half-hourly resolution
   (discharging above zero, charging below).
2. **The same day** — the system imbalance price.
3. **Twelve months** — the typical profile by time of day, with the
   interquartile range.

Periods of negative price are shaded on both day panels, so the link between
the price and what the battery does is visible without cross-referencing.

The two scales (MW and £/MWh) sit in separate panels rather than on a dual
y-axis. A dual axis lets the reader pick whichever correlation they want by
rescaling; two aligned panels say the same thing honestly.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Usage

### 1. Find candidate batteries

Elexon publishes no reliable `fuelType = BATTERY`. What identifies a battery is
that it imports about as much as it exports — a ratio close to 1, where a
950 MW CCGT drawing 10 MW of station load gives 0.01.

```bash
python src/discover_batteries.py --min-mw 20
```

Writes `data/battery_bmus.csv`.

### 2. Screen them for actual activity

Installed capacity is a poor guide. Several large batteries submit a physical
notification flat at zero and record no acceptances at all — nothing to plot.
This step samples a recent window and ranks candidates on what they really do.

```bash
python src/screen_units.py --units 25 --days 14
```

Writes `data/screening.csv`.

### 3. Pick a day worth plotting

A flat price day gives a flat figure. This ranks recent days by intraday price
dispersion; `--by negativePeriods` favours days with negative prices, which
show the charging side most clearly.

```bash
python src/pick_day.py --days 120
```

### 4. Download and plot

```bash
python src/fetch.py --bmu E_STALB-1 --day 2026-07-25 --months 12
python src/make_figure.py --bmu E_STALB-1 --day 2026-07-25 \
    --name "KXP Immingham BESS — 81 MW, UK" --stat mean
```

Output lands in `figures/`. `--lang fr` switches the figure labels to French;
`--stat median` is more robust but understates an asset that is idle much of
the time.

## Physical notifications are not the whole story

Many GB batteries submit a flat zero PN and only move when the system operator
accepts a bid or an offer. Their real operating profile lives in the bid-offer
acceptances (BOALF), not in the PN. The scripts download both and build an
effective profile: the PN, overridden by accepted levels wherever an acceptance
applies.

One consequence worth stating plainly: **the imbalance price is not the price a
battery arbitrages against.** A battery takes positions day-ahead and intraday;
the imbalance price only applies to its unbalanced volume. And part of the
profile comes from acceptances — the system operator ordering the move, for
balancing or for a local network constraint, regardless of the sign of the
system price. The figure shows a loose correlation, not a control loop.

## Layout

```
src/elexon.py              API client (no key required)
src/discover_batteries.py  identify batteries in the BM Unit reference list
src/screen_units.py        rank candidates by actual activity
src/pick_day.py            find a day with price movement
src/fetch.py               download and cache to CSV
src/make_figure.py         build the figure
data/                      local cache (large files are not versioned)
figures/                   output
```

## A note on resolution

Great Britain settles in half-hour periods. Belgium, like most continental
markets, works in quarter-hours. The resolution here is GB's, not Elia's.
