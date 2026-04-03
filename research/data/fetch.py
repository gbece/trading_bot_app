"""
Fetch OHLCV data for BTC/USDT perpetual and other pairs from Binance via ccxt.
Saves to research/data/raw/ as Parquet files.
No API key required for historical OHLCV.

Usage:
    python -m research.data.fetch
    python research/data/fetch.py
"""

from __future__ import annotations
import time
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

import ccxt
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).parent / "raw"

# Symbols: BTC is primary; others are for future cross-validation
SYMBOLS = [
    "BTC/USDT:USDT",  # BTC perpetual — primary research pair
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
]

TIMEFRAMES = ["4h", "1d"]

DATE_START = "2020-01-01"
DATE_END = "2024-12-31"

# ccxt returns timestamps in milliseconds
LIMIT_PER_REQUEST = 1000  # Binance max is 1500; stay conservative
SLEEP_BETWEEN_REQUESTS = 0.5  # seconds — respect rate limits
MAX_RETRIES = 5
RETRY_BACKOFF = 2.0  # seconds, multiplied by retry count


# ---------------------------------------------------------------------------
# File name helpers
# ---------------------------------------------------------------------------

def _symbol_to_filename(symbol: str, timeframe: str) -> str:
    """
    Convert 'BTC/USDT:USDT' + '4h' → 'BTCUSDT_4h.parquet'
    """
    base = symbol.split("/")[0]
    quote = symbol.split("/")[1].split(":")[0]
    tf = timeframe.lower()
    return f"{base}{quote}_{tf}.parquet"


# ---------------------------------------------------------------------------
# Exchange setup
# ---------------------------------------------------------------------------

def _make_exchange() -> ccxt.binanceusdm:
    """Create a Binance USD-M futures exchange instance (no API key needed for public OHLCV)."""
    exchange = ccxt.binanceusdm({
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    })
    return exchange


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def _fetch_ohlcv_with_retry(
    exchange: ccxt.binanceusdm,
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int,
) -> list:
    """Fetch one page of OHLCV with exponential-backoff retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
            return candles
        except (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable) as exc:
            wait = RETRY_BACKOFF * attempt
            logger.warning(
                "Attempt %d/%d failed for %s %s: %s — retrying in %.1fs",
                attempt, MAX_RETRIES, symbol, timeframe, exc, wait,
            )
            time.sleep(wait)
        except ccxt.ExchangeError as exc:
            logger.error("Exchange error for %s %s: %s — aborting", symbol, timeframe, exc)
            raise
    raise RuntimeError(
        f"Failed to fetch {symbol} {timeframe} after {MAX_RETRIES} attempts"
    )


def fetch_pair(
    exchange: ccxt.binanceusdm,
    symbol: str,
    timeframe: str,
    date_start: str = DATE_START,
    date_end: str = DATE_END,
) -> pd.DataFrame:
    """
    Paginate through all OHLCV candles for the given symbol/timeframe/range.
    Returns a DataFrame with columns: [timestamp, open, high, low, close, volume].
    All timestamps are UTC-aware.
    """
    start_dt = datetime.strptime(date_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(date_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    since_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    all_candles: list = []
    logger.info("Fetching %s %s from %s to %s", symbol, timeframe, date_start, date_end)

    while True:
        candles = _fetch_ohlcv_with_retry(exchange, symbol, timeframe, since_ms, LIMIT_PER_REQUEST)

        if not candles:
            break

        # Filter to requested range (inclusive start, inclusive end date)
        candles = [c for c in candles if c[0] <= end_ms]
        all_candles.extend(candles)

        last_ts = candles[-1][0]
        logger.debug("  fetched %d candles, last ts=%d", len(candles), last_ts)

        if last_ts >= end_ms or len(candles) < LIMIT_PER_REQUEST:
            break

        # Advance: next page starts one candle after last received
        since_ms = last_ts + 1
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    if not all_candles:
        raise ValueError(f"No data returned for {symbol} {timeframe}")

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)

    # Final clip to requested range
    df = df[df["timestamp"] <= pd.Timestamp(date_end, tz="UTC") + pd.Timedelta(days=1)]
    df = df[df["timestamp"] >= pd.Timestamp(date_start, tz="UTC")]

    logger.info("  → %d candles for %s %s", len(df), symbol, timeframe)
    return df


def save_pair(df: pd.DataFrame, symbol: str, timeframe: str, raw_dir: Path = RAW_DIR) -> Path:
    """Save DataFrame as Parquet to raw_dir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    filename = _symbol_to_filename(symbol, timeframe)
    path = raw_dir / filename
    df.to_parquet(path, index=False)
    logger.info("Saved %s → %s", filename, path)
    return path


def load_pair(symbol: str, timeframe: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load a previously saved Parquet file."""
    filename = _symbol_to_filename(symbol, timeframe)
    path = raw_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    df = pd.read_parquet(path)
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    return df


# ---------------------------------------------------------------------------
# Main: fetch all pairs
# ---------------------------------------------------------------------------

def fetch_all(
    symbols: list[str] = SYMBOLS,
    timeframes: list[str] = TIMEFRAMES,
    date_start: str = DATE_START,
    date_end: str = DATE_END,
    raw_dir: Path = RAW_DIR,
) -> None:
    """
    Fetch all symbol/timeframe combinations and save as Parquet files.
    Skips any file that already exists.
    """
    exchange = _make_exchange()

    for symbol in symbols:
        for timeframe in timeframes:
            filename = _symbol_to_filename(symbol, timeframe)
            path = raw_dir / filename
            if path.exists():
                logger.info("Skipping %s (already exists)", filename)
                continue
            df = fetch_pair(exchange, symbol, timeframe, date_start, date_end)
            save_pair(df, symbol, timeframe, raw_dir)
            time.sleep(SLEEP_BETWEEN_REQUESTS)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    fetch_all()
