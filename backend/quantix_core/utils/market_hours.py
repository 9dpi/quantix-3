from datetime import datetime, timezone, time
from loguru import logger

class MarketHours:
    """Utility to check if Forex market is open (UTC based)."""
    
    @staticmethod
    def is_market_open() -> bool:
        """
        Check if Forex market is currently open.
        Opens Sunday 22:00 UTC
        Closes Friday 22:00 UTC
        """
        now = datetime.now(timezone.utc)
        weekday = now.weekday() # 0 = Monday, 1 = Tuesday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday
        hour = now.hour
        
        # Friday close (22:00 UTC)
        if weekday == 4 and hour >= 22:
            return False
        
        # Saturday (Closed)
        if weekday == 5:
            return False
            
        # Sunday open (22:00 UTC)
        if weekday == 6 and hour < 22:
            return False
            
        return True

    @staticmethod
    def should_generate_signals() -> bool:
        """
        Safety check: Don't generate new signals in low-quality periods.
        - Friday after 17:00 UTC (pre-weekend)
        - Sunday before Mon 00:00 UTC (low liquidity opening)
        - Rollover hours (21:00-23:00 UTC) — high spread
        """
        if not MarketHours.is_market_open():
            return False
            
        now = datetime.now(timezone.utc)
        
        # Friday safety buffer (Market gets thin after 17:00 UTC)
        if now.weekday() == 4 and now.hour >= 17:
            logger.warning("🕒 Market liquidity dropping near weekend. Skipping new signal generation.")
            return False
        
        # Sunday opening: market opens 22:00 UTC Sunday but has terrible liquidity until Monday
        if now.weekday() == 6:  # Sunday
            logger.warning("🕒 Sunday session: Liquidity too low for reliable signals.")
            return False
        
        # Monday early hours (before 01:00 UTC) — continuation of Sunday thin liquidity
        if now.weekday() == 0 and now.hour < 1:
            logger.warning("🕒 Monday early hours: Skipping signal due to thin liquidity.")
            return False
        
        # Daily rollover window (21:00-23:00 UTC) — spread widens significantly
        if 21 <= now.hour <= 23:
            logger.warning("🕒 Rollover window (21-23 UTC): High spread, skipping signal.")
            return False
            
        return True
