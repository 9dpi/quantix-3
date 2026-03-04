"""
Quantix Feed Sources
====================
Provides a unified interface for market data feeds.

Available Sources:
- binance_proxy : Uses Binance REST API as a proxy for forex EURUSD (Phase 1 default)
- mt5_api       : MetaTrader5 Python API — requires local MT5 installation (Phase 2A)
- ctrader_api   : cTrader Open API — requires Pepperstone cTrader credentials (Phase 2B)
"""

from .binance_feed import BinanceFeed
from .base_feed import BaseFeed

__all__ = ["BaseFeed", "BinanceFeed", "get_feed"]


def get_feed(feed_source: str = "binance_proxy", **kwargs) -> "BaseFeed":
    """
    Factory function — returns the correct feed instance by name.

    Args:
        feed_source: "binance_proxy" | "mt5_api" | "ctrader_api"
        **kwargs:    Extra init arguments forwarded to the feed class
    """
    if feed_source == "binance_proxy":
        return BinanceFeed(**kwargs)

    if feed_source == "mt5_api":
        from .mt5_feed import MT5Feed
        return MT5Feed(**kwargs)

    if feed_source == "ctrader_api":
        from .ctrader_feed import CTraderFeed
        return CTraderFeed(**kwargs)

    raise ValueError(f"Unknown feed source: '{feed_source}'. "
                     f"Valid options: binance_proxy | mt5_api | ctrader_api")
