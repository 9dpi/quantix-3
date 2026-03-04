"""
MT5Feed — Phase 2A: MetaTrader 5 Python API Feed
=================================================
Connects to a locally-running MT5 terminal (Pepperstone) and fetches
real bid/ask prices directly — no proxying, no spread estimation.

Prerequisites (Step 2A.1 from VALIDATION_ROADMAP.md):
    pip install MetaTrader5
    - MT5 installed and logged into Pepperstone account
    - "Algo Trading" / "Allow DLL imports" enabled in MT5 tools menu
    - Python process must run on the SAME machine as MT5 (Windows only)

Usage:
    feed = MT5Feed()
    if feed.is_available():
        data = feed.get_price("EURUSD")

Environment variable override:
    MT5_LOGIN   – Account number (int)
    MT5_PASSWORD – Account password
    MT5_SERVER   – Server name e.g. "Pepperstone-Demo"
"""

import os
from datetime import datetime, timezone
from typing import Optional, Dict

from .base_feed import BaseFeed


class MT5Feed(BaseFeed):
    """
    MetaTrader 5 Python API feed.

    Strengths : Real Pepperstone bid/ask, real spread, no proxy drift.
    Weakness  : Windows-only, MT5 terminal must be running locally.
                Cannot run on Railway — designed for local observer mode.
    """

    def __init__(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ):
        # Read credentials from args or environment
        self.login    = login    or (int(os.getenv("MT5_LOGIN", "0")) or None)
        self.password = password or os.getenv("MT5_PASSWORD")
        self.server   = server   or os.getenv("MT5_SERVER", "Pepperstone-Demo")
        self._mt5     = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> bool:
        """
        Try to load MetaTrader5 library and initialize the connection.
        Returns True on success. Safe to call repeatedly.
        """
        if self._initialized:
            return True

        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 package not installed. "
                "Run: pip install MetaTrader5   (Windows only)"
            )

        # Initialize MT5 connection
        init_kwargs: dict = {}
        if self.login:
            init_kwargs["login"]    = self.login
            init_kwargs["password"] = self.password
            init_kwargs["server"]   = self.server

        ok = self._mt5.initialize(**init_kwargs)

        if not ok:
            err = self._mt5.last_error()
            raise RuntimeError(
                f"MT5 initialization failed: {err}\n"
                f"Make sure MT5 terminal is running and Algo Trading is enabled."
            )

        self._initialized = True
        return True

    def _ensure_symbol(self, symbol: str) -> bool:
        """Enable a symbol in MT5 Market Watch if not already visible."""
        if not self._mt5.symbol_info(symbol):
            return False
        if not self._mt5.symbol_info(symbol).visible:
            self._mt5.symbol_select(symbol, True)
        return True

    # ------------------------------------------------------------------
    # BaseFeed contract
    # ------------------------------------------------------------------

    def get_price(self, symbol: str = "EURUSD") -> Optional[Dict]:
        """
        Fetch current tick (bid/ask) and latest 1m OHLC from MT5.

        Returns the real Pepperstone spread — no estimation needed.
        """
        try:
            self._ensure_initialized()
            self._ensure_symbol(symbol)

            # Real-time tick (bid / ask)
            tick = self._mt5.symbol_info_tick(symbol)
            if tick is None:
                return None

            bid = tick.bid
            ask = tick.ask
            spread_pips = round((ask - bid) * 10000, 2)  # For 5-decimal pairs

            # Latest 1m candle for OHLC (needed by the validator)
            import MetaTrader5 as mt5
            rates = self._mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
            if rates is None or len(rates) == 0:
                # Fallback: synthesize candle from tick
                candle_open = candle_high = candle_low = candle_close = bid
            else:
                r = rates[0]
                candle_open  = float(r["open"])
                candle_high  = float(r["high"])
                candle_low   = float(r["low"])
                candle_close = float(r["close"])

            ts = datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat()

            return {
                "timestamp":   ts,
                "open":        candle_open,
                "high":        candle_high,
                "low":         candle_low,
                "close":       candle_close,
                "bid":         round(bid, 5),
                "ask":         round(ask, 5),
                "spread_pips": spread_pips,
                "source":      f"mt5_api ({self.server})",
            }

        except Exception as e:
            # Caller decides what to do — just return None
            return None

    def is_available(self) -> bool:
        """Check if MT5 terminal is running and connected."""
        try:
            self._ensure_initialized()
            info = self._mt5.terminal_info()
            return info is not None and info.connected
        except Exception:
            return False

    def shutdown(self):
        """Gracefully close the MT5 connection."""
        if self._initialized and self._mt5:
            self._mt5.shutdown()
            self._initialized = False
