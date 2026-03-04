"""
BaseFeed — Abstract interface that all feed sources must implement.
==================================================================
By enforcing a single contract, the validator can swap feeds at runtime
without changing any validation logic.

Required contract:
    get_price(symbol) → Dict  {open, high, low, close, bid, ask, timestamp, source}
    is_available()    → bool  Can this feed currently connect?
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict


class BaseFeed(ABC):
    """Abstract base class for all market data feed adapters."""

    @abstractmethod
    def get_price(self, symbol: str = "EURUSD") -> Optional[Dict]:
        """
        Fetch current market data for a symbol.

        Returns dict with keys:
            - timestamp  : ISO 8601 UTC string
            - open       : float
            - high       : float
            - low        : float
            - close      : float
            - bid        : float  (best approximation if unavailable)
            - ask        : float  (best approximation if unavailable)
            - spread_pips: float  (ask - bid in pips)
            - source     : str    (human-readable feed name)

        Returns None on failure.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the feed is reachable (connectivity check)."""

    @property
    def name(self) -> str:
        return self.__class__.__name__
