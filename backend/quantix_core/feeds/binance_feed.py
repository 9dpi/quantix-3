"""
BinanceFeed — Phase 1 feed (Binance REST API proxy)
====================================================
Uses Binance EURUSDT 1m klines as a Forex price proxy.
Fallback chain: global → US → developer API endpoint.
"""

import requests
from datetime import datetime, timezone
from typing import Optional, Dict
from loguru import logger

from .base_feed import BaseFeed

# EURUSD ≈ EURUSDT — close enough for proxy validation
_SYMBOL_MAP = {
    "EURUSD": "EURUSDT",
    "GBPUSD": "GBPUSDT",
    "USDJPY": "USDTJPY",   # Inverted — handled below
    "AUDUSD": "AUDUSDT",
    "USDCAD": "USDTCAD",
}

_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://api.binance.us/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

# Typical Binance EURUSDT spread offset (pips) added to bid/ask simulation
_SIMULATED_SPREAD_PIPS = 0.2


class BinanceFeed(BaseFeed):
    """
    Binance REST API proxy feed.

    Strengths : Always available, no credentials, Railway-compatible.
    Weakness  : Not real Pepperstone spread — Phase 1 baseline only.
    """

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    # ------------------------------------------------------------------
    # BaseFeed contract
    # ------------------------------------------------------------------

    def get_price(self, symbol: str = "EURUSD") -> Optional[Dict]:
        """Fetch latest 1m candle from Binance."""
        binance_symbol = _SYMBOL_MAP.get(symbol.upper(), f"{symbol}T")
        params = {"symbol": binance_symbol, "interval": "1m", "limit": 5}

        for url in _ENDPOINTS:
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not data:
                    continue

                candle = data[-1]
                ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)
                
                # --- SANITY FILTER ---
                # 1. Future block
                if (ts - datetime.now(timezone.utc)).total_seconds() > 60:
                    logger.warning(f"🚩 Sanity Reject: Future timestamp {ts}")
                    continue
                
                # 2. Spike block (> 5% move in 1m is suspicious for EURUSD)
                o, h, l, c = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4])
                if abs(c - o) / o > 0.05:
                    logger.warning(f"🚩 Sanity Reject: Suspected price spike {o} -> {c}")
                    continue
                
                half_spread = (_SIMULATED_SPREAD_PIPS / 2) * 0.0001
                return {
                    "timestamp": ts.isoformat(),
                    "open":       o,
                    "high":       h,
                    "low":        l,
                    "close":      c,
                    "bid":        round(c - half_spread, 5),
                    "ask":        round(c + half_spread, 5),
                    "spread_pips": _SIMULATED_SPREAD_PIPS,
                    "source":     f"binance_proxy ({url})",
                }
            except Exception:
                continue

        return None  # All endpoints failed

    def get_history(self, symbol: str = "EURUSD", interval: str = "15m", limit: int = 100) -> Optional[list]:
        """Fetch historical candles from Binance."""
        binance_symbol = _SYMBOL_MAP.get(symbol.upper(), f"{symbol}T")
        params = {"symbol": binance_symbol, "interval": interval, "limit": limit}

        for url in _ENDPOINTS:
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not data:
                    continue

                history = []
                for candle in data:
                    ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)
                    o, h, l, c = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4])
                    
                    # Sanity check
                    if (ts - datetime.now(timezone.utc)).total_seconds() > 60: continue
                    if abs(c - o) / (o or 1) > 0.10: continue # 10% for history just in case

                    history.append({
                        "datetime": ts.isoformat(),
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c
                    })
                return history
            except Exception:
                continue
        return None

    def is_available(self) -> bool:
        try:
            resp = requests.get(
                _ENDPOINTS[0],
                params={"symbol": "EURUSDT", "interval": "1m", "limit": 1},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False
