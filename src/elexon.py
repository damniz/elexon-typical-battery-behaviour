"""Minimal client for the Elexon Insights (BMRS) API.

Public API, no key required: https://developer.data.elexon.co.uk/
Base URL: https://data.elexon.co.uk/bmrs/api/v1

Data is published under the Elexon licence; any reuse must credit Elexon
as the source.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
TIMEOUT = 60

_session = requests.Session()
_session.headers.update({"Accept": "application/json"})


def _iso(ts: datetime) -> str:
    """Timestamp in the format the API expects (UTC)."""
    return ts.strftime("%Y-%m-%dT%H:%MZ")


def _get(path: str, params: dict | None = None, retries: int = 4) -> Any:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            response = _session.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"GET {url} params={params} failed") from exc
            time.sleep(2 ** attempt)


def _frame(payload: Any) -> pd.DataFrame:
    """The API returns either a bare array or an object with a "data" key."""
    if isinstance(payload, dict):
        payload = payload.get("data", [])
    return pd.DataFrame(payload)


def bm_units() -> pd.DataFrame:
    """Reference list of every BM Unit (a few thousand rows)."""
    return _frame(_get("/reference/bmunits/all"))


def physical(
    bm_unit: str,
    start: datetime,
    end: datetime,
    dataset: str = "PN",
    chunk_days: int = 7,
) -> pd.DataFrame:
    """Physical data for one BM Unit, chunked to stay within API limits.

    dataset: PN (physical notification), QPN, MELS, MILS.
    Each row carries levelFrom / levelTo (MW) over the [timeFrom, timeTo] span.
    """
    frames: list[pd.DataFrame] = []
    cursor, step = start, timedelta(days=chunk_days)
    while cursor < end:
        stop = min(cursor + step, end)
        frames.append(
            _frame(
                _get(
                    "/balancing/physical",
                    {
                        "bmUnit": bm_unit,
                        "dataset": dataset,
                        "from": _iso(cursor),
                        "to": _iso(stop),
                    },
                )
            )
        )
        cursor = stop

    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    for column in ("timeFrom", "timeTo"):
        df[column] = pd.to_datetime(df[column], utc=True)
    return (
        df.sort_values("timeFrom")
        .drop_duplicates(subset=["timeFrom", "timeTo", "levelFrom", "levelTo"])
        .reset_index(drop=True)
    )


def acceptances_for_unit(
    bm_unit: str,
    start: datetime,
    end: datetime,
    chunk_days: int = 7,
) -> pd.DataFrame:
    """Bid-offer acceptances (BOALF) for one BM Unit.

    Many GB batteries submit a flat zero physical notification and only move
    when the system operator accepts a bid or an offer. For those assets the
    real operating profile lives here, not in the PN.
    """
    frames: list[pd.DataFrame] = []
    cursor, step = start, timedelta(days=chunk_days)
    while cursor < end:
        stop = min(cursor + step, end)
        frames.append(
            _frame(
                _get(
                    "/balancing/acceptances",
                    {"bmUnit": bm_unit, "from": _iso(cursor), "to": _iso(stop)},
                )
            )
        )
        cursor = stop

    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    for column in ("timeFrom", "timeTo", "acceptanceTime"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], utc=True)
    sort_keys = [c for c in ("acceptanceTime", "acceptanceNumber", "timeFrom")
                 if c in df.columns]
    return df.sort_values(sort_keys).reset_index(drop=True)


def system_prices(day: date) -> pd.DataFrame:
    """Imbalance prices (system buy / system sell) for one settlement date."""
    df = _frame(_get(f"/balancing/settlement/system-prices/{day:%Y-%m-%d}"))
    if df.empty:
        return df
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    return df.sort_values("startTime").reset_index(drop=True)
