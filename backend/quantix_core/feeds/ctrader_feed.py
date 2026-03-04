"""
CTraderFeed — Phase 2B: cTrader Open API Feed (Alternative to MT5)
===================================================================
Uses the Pepperstone cTrader Open API to stream real bid/ask prices.
This is the cross-platform alternative to MT5 (works on Linux/Railway).

Prerequisites (Step 2B.1 from VALIDATION_ROADMAP.md):
    pip install ctrader-open-api
    - Pepperstone cTrader account (live or demo)
    - App registered at https://openapi.ctrader.com/
    - Client ID and Client Secret from registered app
    - Access Token obtained via OAuth 2.0 flow

Environment variables:
    CTRADER_CLIENT_ID      – App Client ID
    CTRADER_CLIENT_SECRET  – App Client Secret
    CTRADER_ACCESS_TOKEN   – OAuth access token
    CTRADER_ACCOUNT_ID     – Pepperstone cTrader account ID (int)
    CTRADER_DEMO           – "true" for demo, "false" for live (default: "true")

Status: STUB — async adapter skeleton ready; OAuth + subscribe logic
        should be completed in Phase 2B.2 (Days 3-5).
"""

import os
from typing import Optional, Dict

from .base_feed import BaseFeed


class CTraderFeed(BaseFeed):
    """
    cTrader Open API feed (Phase 2B alternative).

    Strengths : Cross-platform (Linux/Railway compatible), real spreads.
    Weakness  : Async event-driven — requires an event loop wrapper.
                Token refresh logic not yet implemented.

    NOTE: This is a stub implementation. The __init__ sets up config
    and is_available() does a TCP connectivity check. get_price() raises
    NotImplementedError until the async event loop bridge is built.
    """

    DEMO_HOST = "demo.ctraderapi.com"
    LIVE_HOST = "live.ctraderapi.com"
    PORT = 5035

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        account_id: Optional[int] = None,
        demo: bool = True,
    ):
        self.client_id     = client_id     or os.getenv("CTRADER_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CTRADER_CLIENT_SECRET")
        self.access_token  = access_token  or os.getenv("CTRADER_ACCESS_TOKEN")
        self.account_id    = account_id    or int(os.getenv("CTRADER_ACCOUNT_ID", "0") or 0)
        env_demo           = os.getenv("CTRADER_DEMO", "true").lower() == "true"
        self.demo          = demo if demo is not True else env_demo
        self.host          = self.DEMO_HOST if self.demo else self.LIVE_HOST

        self._validate_config()

    def _validate_config(self):
        """Warn if required credentials are missing."""
        missing = [
            k for k, v in {
                "client_id":    self.client_id,
                "access_token": self.access_token,
                "account_id":   self.account_id,
            }.items() if not v
        ]
        if missing:
            import warnings
            warnings.warn(
                f"CTraderFeed: missing credentials — {missing}. "
                "Set CTRADER_CLIENT_ID / CTRADER_ACCESS_TOKEN / CTRADER_ACCOUNT_ID.",
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # BaseFeed contract
    # ------------------------------------------------------------------

    def get_price(self, symbol: str = "EURUSD") -> Optional[Dict]:
        """
        NOT YET IMPLEMENTED (Phase 2B Day 3-5).

        The cTrader Open API is event-driven (Twisted/asyncio).
        A synchronous bridge (run_until_complete pattern) must be added
        to make this compatible with the existing validator loop.

        Raises NotImplementedError so callers can gracefully fall back.
        """
        raise NotImplementedError(
            "CTraderFeed.get_price() is a Phase 2B stub. "
            "Async event loop bridge not yet implemented. "
            "Use BinanceFeed or MT5Feed for now."
        )

    def is_available(self) -> bool:
        """
        Simple TCP reachability check to cTrader API host.
        Does NOT validate credentials.
        """
        import socket
        try:
            with socket.create_connection((self.host, self.PORT), timeout=5):
                return True
        except (OSError, ConnectionRefusedError):
            return False
