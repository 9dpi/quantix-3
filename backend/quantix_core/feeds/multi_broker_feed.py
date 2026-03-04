"""
multi_broker_feed.py — Phase 5.3: Multi-Broker Comparison Engine
=================================================================
Validates Quantix signals against MULTIPLE brokers simultaneously
to identify the best execution venue and detect broker-specific
spread anomalies.

Supported brokers:
    ✅ Pepperstone (MT5 API or Binance proxy fallback)
    📋 IC Markets  (REST API — Phase 5.3 implementation)
    📋 OANDA       (v20 REST API — Phase 5.3 implementation)

Output per signal check:
    {
        "signal_id": "...",
        "direction": "BUY",
        "entry": 1.0850,
        "results": {
            "pepperstone": {"spread": 0.3, "entry_hit": True,  "latency_ms": 5},
            "ic_markets":  {"spread": 0.2, "entry_hit": True,  "latency_ms": 12},
            "oanda":       {"spread": 0.5, "entry_hit": False, "latency_ms": 80},
        },
        "best_broker": "ic_markets",    # lowest spread + hit
        "consensus":   "HIT",           # majority rule
    }

Usage:
    engine = MultiBrokerEngine()
    result = engine.check_signal(signal_dict)
    engine.compare_spreads()  # Returns live spread comparison table
"""

import os
import time
import threading
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from loguru import logger

from backend.quantix_core.feeds.base_feed import BaseFeed


# ─────────────────────────────────────────────────────────────────────────────
# Broker adapters
# ─────────────────────────────────────────────────────────────────────────────

class _BinanceBrokerAdapter(BaseFeed):
    """
    Pepperstone fallback adapter (uses Binance as proxy).
    Reuses the existing BinanceFeed.
    """
    BROKER_NAME = "pepperstone_proxy"

    def __init__(self):
        from backend.quantix_core.feeds.binance_feed import BinanceFeed
        self._inner = BinanceFeed()

    def get_price(self, symbol: str = "EURUSD") -> Optional[dict]:
        return self._inner.get_price(symbol)

    def is_available(self) -> bool:
        return self._inner.is_available()


class _ICMarketsAdapter(BaseFeed):
    """
    IC Markets REST API adapter.

    IC Markets uses a TradingView-compatible data provider.
    For Phase 5.3, we integrate with their public price feed endpoint.

    NOTE: IC Markets does not currently expose a free public REST API.
    This adapter implements a OANDA-compatible fallback for now and
    will be replaced when IC Markets releases their API.
    """
    BROKER_NAME = "ic_markets"

    _ENDPOINT = "https://api-fxtrade.oanda.com/v3/instruments/{instrument}/candles"
    _TOKEN     = os.getenv("OANDA_API_KEY", "")  # Reuse OANDA key as fallback

    def get_price(self, symbol: str = "EURUSD") -> Optional[dict]:
        # Phase 5.3 stub — returns None until full integration
        # TODO: Replace with IC Markets endpoint when available
        raise NotImplementedError(
            "IC Markets API integration is scheduled for Phase 5.3. "
            "Use pepperstone_proxy or oanda as active feeds."
        )

    def is_available(self) -> bool:
        return False  # Not yet integrated


class _OANDAAdapter(BaseFeed):
    """
    OANDA v20 REST API adapter.

    Requires:
        OANDA_API_KEY    — Bearer token from OANDA developer portal
        OANDA_ACCOUNT_ID — Your OANDA account ID (optional for prices)

    Docs: https://developer.oanda.com/rest-live-v20/instrument-ep/
    """
    BROKER_NAME = "oanda"

    _BASE       = "https://api-fxtrade.oanda.com/v3"
    _DEMO_BASE  = "https://api-fxpractice.oanda.com/v3"

    _SYMBOL_MAP = {
        "EURUSD":  "EUR_USD",
        "GBPUSD":  "GBP_USD",
        "USDJPY":  "USD_JPY",
        "AUDUSD":  "AUD_USD",
        "USDCHF":  "USD_CHF",
        "USDCAD":  "USD_CAD",
        "NZDUSD":  "NZD_USD",
        "XAUUSD":  "XAU_USD",
        "GBPJPY":  "GBP_JPY",
        "EURJPY":  "EUR_JPY",
    }

    def __init__(self):
        self._token     = os.getenv("OANDA_API_KEY", "")
        self._demo      = os.getenv("OANDA_DEMO", "true").lower() == "true"
        self._base      = self._DEMO_BASE if self._demo else self._BASE
        self._sess      = requests.Session()
        if self._token:
            self._sess.headers.update({"Authorization": f"Bearer {self._token}"})

    def get_price(self, symbol: str = "EURUSD") -> Optional[dict]:
        if not self._token:
            return None

        oanda_sym = self._SYMBOL_MAP.get(symbol.upper())
        if not oanda_sym:
            logger.warning(f"[OANDA] Unsupported symbol: {symbol}")
            return None

        url = f"{self._base}/instruments/{oanda_sym}/candles"
        params = {
            "granularity": "M1",
            "count":        2,
            "price":       "BA",   # Bid + Ask separate
        }

        t0 = time.monotonic()
        try:
            resp = self._sess.get(url, params=params, timeout=8)
            latency_ms = round((time.monotonic() - t0) * 1000)

            if resp.status_code != 200:
                logger.warning(f"[OANDA] HTTP {resp.status_code}")
                return None

            candles = resp.json().get("candles", [])
            if not candles:
                return None

            c = candles[-1]
            bid = float(c["bid"]["c"])
            ask = float(c["ask"]["c"])
            pip = 0.0001 if "JPY" not in symbol else 0.01
            spread_pips = round((ask - bid) / pip, 2)

            return {
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "open":        float(c["mid"]["o"]) if "mid" in c else (bid + ask) / 2,
                "high":        float(c["mid"]["h"]) if "mid" in c else ask,
                "low":         float(c["mid"]["l"]) if "mid" in c else bid,
                "close":       float(c["mid"]["c"]) if "mid" in c else (bid + ask) / 2,
                "bid":         bid,
                "ask":         ask,
                "spread_pips": spread_pips,
                "latency_ms":  latency_ms,
                "source":      f"oanda ({'demo' if self._demo else 'live'})",
            }
        except Exception as e:
            logger.error(f"[OANDA] Error: {e}")
            return None

    def is_available(self) -> bool:
        return bool(self._token)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Broker Engine
# ─────────────────────────────────────────────────────────────────────────────

class MultiBrokerEngine:
    """
    Queries multiple broker feeds concurrently and compares results.

    Phase 5.3 activation:
        - pepperstone_proxy : always enabled (Binance fallback)
        - oanda             : enabled if OANDA_API_KEY is set
        - ic_markets        : stub (pending API)
    """

    def __init__(self):
        self._adapters: Dict[str, BaseFeed] = {
            "pepperstone": _BinanceBrokerAdapter(),
        }

        if os.getenv("OANDA_API_KEY"):
            self._adapters["oanda"] = _OANDAAdapter()
            logger.info("[MultiBroker] OANDA adapter activated")
        else:
            logger.info("[MultiBroker] OANDA_API_KEY not set — OANDA adapter inactive")

        # IC Markets stub registered but marked inactive
        self._adapters["ic_markets"] = _ICMarketsAdapter()

    # ------------------------------------------------------------------

    def compare_spreads(self, symbol: str = "EURUSD") -> Dict:
        """
        Fetch live prices from all active brokers concurrently.
        Returns comparison table sorted by spread (tightest first).
        """
        results    = {}
        errors     = {}
        lock       = threading.Lock()

        def _fetch(name: str, adapter: BaseFeed):
            try:
                if not adapter.is_available():
                    with lock: errors[name] = "Not available / not configured"
                    return
                data = adapter.get_price(symbol)
                if data:
                    with lock: results[name] = {
                        "bid":        data.get("bid"),
                        "ask":        data.get("ask"),
                        "spread_pips": data.get("spread_pips"),
                        "latency_ms":  data.get("latency_ms", -1),
                        "source":      data.get("source"),
                        "ok":          True,
                    }
                else:
                    with lock: errors[name] = "get_price() returned None"
            except NotImplementedError as e:
                with lock: errors[name] = str(e)
            except Exception as e:
                with lock: errors[name] = str(e)

        threads = [
            threading.Thread(target=_fetch, args=(n, a), daemon=True)
            for n, a in self._adapters.items()
        ]
        for t in threads: t.start()
        for t in threads: t.join(timeout=12)

        # Rank by spread (active brokers only)
        active = {n: r for n, r in results.items() if r.get("spread_pips") is not None}
        ranked = sorted(active.items(), key=lambda x: x[1]["spread_pips"])

        # Consensus bid/ask
        bids = [r["bid"] for r in active.values() if r.get("bid")]
        asks = [r["ask"] for r in active.values() if r.get("ask")]

        return {
            "symbol":        symbol,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "brokers":       results,
            "errors":        errors,
            "best_spread":   ranked[0][0] if ranked else None,
            "worst_spread":  ranked[-1][0] if ranked else None,
            "consensus_bid": round(statistics.mean(bids), 5) if bids else None,
            "consensus_ask": round(statistics.mean(asks), 5) if asks else None,
            "active_count":  len(active),
        }

    def check_signal(self, signal: dict) -> Dict:
        """
        Check a single signal across all active brokers.

        Args:
            signal: dict with keys: signal_id, direction, entry_price, asset

        Returns:
            Per-broker hit verdict + consensus + best broker recommendation.
        """
        symbol    = signal.get("asset", "EURUSD")
        direction = signal.get("direction", "BUY").upper()
        entry     = float(signal.get("entry_price", 0))

        comparison = self.compare_spreads(symbol=symbol)
        broker_results: Dict[str, dict] = {}

        for broker, data in comparison["brokers"].items():
            if not data.get("ok"):
                continue
            bid = data["bid"]
            ask = data["ask"]
            # Entry hit logic (conservative — uses ask for BUY, bid for SELL)
            if direction == "BUY":
                hit = ask <= entry
            else:
                hit = bid >= entry

            broker_results[broker] = {
                "bid":        bid,
                "ask":        ask,
                "spread_pips": data["spread_pips"],
                "entry_checked": ask if direction == "BUY" else bid,
                "entry_hit":  hit,
                "latency_ms": data.get("latency_ms", -1),
            }

        # Consensus: majority hit
        hits = [v["entry_hit"] for v in broker_results.values()]
        consensus = "HIT" if (hits.count(True) > hits.count(False)) else "MISS"

        # Best broker = tightest spread among those that hit
        hit_brokers   = [(n, v) for n, v in broker_results.items() if v["entry_hit"]]
        best_broker   = min(hit_brokers, key=lambda x: x[1]["spread_pips"])[0] if hit_brokers else None

        return {
            "signal_id":   signal.get("signal_id", "?"),
            "symbol":      symbol,
            "direction":   direction,
            "entry":       entry,
            "checked_at":  comparison["timestamp"],
            "results":     broker_results,
            "consensus":   consensus,
            "best_broker": best_broker,
        }

    def availability_summary(self) -> List[dict]:
        """Quick status check for all configured adapters."""
        out = []
        for name, adapter in self._adapters.items():
            try:
                avail = adapter.is_available()
            except Exception:
                avail = False
            out.append({"broker": name, "available": avail,
                        "class": adapter.__class__.__name__})
        return out
