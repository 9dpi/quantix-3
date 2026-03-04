from typing import Tuple, Optional
from loguru import logger
from backend.quantix_core.engine.primitives.fvg_detector import FairValueGap


class EntryCalculator:
    """
    Calculates and validates entry prices for trading signals.
    
    Strategy: Dynamic FVG Entry (New) with Fixed Offset Fallback.
    - BUY: Entry at Bullish FVG midpoint below market.
    - SELL: Entry at Bearish FVG midpoint above market.
    """
    
    def __init__(
        self,
        offset_pips: float = 5.0,
        min_distance_pips: float = 1.0,
        max_distance_pips: float = 50.0
    ):
        """
        Initialize entry calculator with configuration.
        
        Args:
            offset_pips: Default offset from market price in pips
            min_distance_pips: Minimum allowed distance in pips
            max_distance_pips: Maximum allowed distance in pips
        """
        self.offset = offset_pips * 0.0001  # Convert pips to price
        self.min_distance = min_distance_pips * 0.0001
        self.max_distance = max_distance_pips * 0.0001
        
        logger.info(
            f"EntryCalculator initialized: "
            f"offset={offset_pips} pips, "
            f"min={min_distance_pips} pips, "
            f"max={max_distance_pips} pips"
        )
    
    def calculate_entry_price(
        self,
        market_price: float,
        direction: str,
        custom_offset: float = None
    ) -> float:
        """
        Calculate entry price for future entry signal.
        
        Args:
            market_price: Current market price (P₀)
            direction: "BUY" or "SELL"
            custom_offset: Optional custom offset (in price, not pips)
        
        Returns:
            Entry price (E) where E ≠ P₀
        
        Raises:
            ValueError: If direction is invalid
        
        Example:
            >>> calc = EntryCalculator(offset_pips=5.0)
            >>> calc.calculate_entry_price(1.19371, "BUY")
            1.19321  # 5 pips below market
        """
        offset = custom_offset if custom_offset is not None else self.offset
        
        if direction == "BUY":
            entry = market_price - offset
        elif direction == "SELL":
            entry = market_price + offset
        else:
            raise ValueError(f"Invalid direction: {direction}. Must be 'BUY' or 'SELL'")
        
        # Round to 5 decimal places (standard for EURUSD)
        entry = round(entry, 5)
        
        logger.debug(
            f"Calculated entry: market={market_price}, "
            f"direction={direction}, offset={offset:.5f}, entry={entry}"
        )
        
        return entry
    
    def validate_entry_price(
        self,
        entry: float,
        market_price: float,
        direction: str
    ) -> Tuple[bool, str]:
        """
        Validate entry price meets all requirements.
        
        Args:
            entry: Proposed entry price
            market_price: Current market price
            direction: "BUY" or "SELL"
        
        Returns:
            (is_valid, error_message)
            - is_valid: True if entry is valid
            - error_message: Description of error, or "Valid" if no error
        
        Validation Rules:
            1. Entry ≠ Market Price (min distance check)
            2. Entry in correct direction (BUY below, SELL above)
            3. Entry not too far from market (max distance check)
        
        Example:
            >>> calc = EntryCalculator()
            >>> is_valid, msg = calc.validate_entry_price(1.19321, 1.19371, "BUY")
            >>> print(is_valid, msg)
            True, "Valid"
        """
        distance = abs(entry - market_price)
        
        # Check 1: Entry ≠ Market Price (minimum distance)
        if distance < self.min_distance:
            return False, (
                f"Entry too close to market: "
                f"distance={distance:.5f} < min={self.min_distance:.5f}"
            )
        
        # Check 2: Entry in correct direction
        if direction == "BUY" and entry >= market_price:
            return False, (
                f"BUY entry must be below market: "
                f"entry={entry} >= market={market_price}"
            )
        
        if direction == "SELL" and entry <= market_price:
            return False, (
                f"SELL entry must be above market: "
                f"entry={entry} <= market={market_price}"
            )
        
        # Check 3: Entry not too far from market
        if distance > self.max_distance:
            return False, (
                f"Entry too far from market: "
                f"distance={distance:.5f} > max={self.max_distance:.5f}"
            )
        
        return True, "Valid"
    
    def calculate_fvg_entry(
        self,
        market_price: float,
        direction: str,
        fvg: Optional[FairValueGap] = None
    ) -> Tuple[float, bool, str]:
        """
        Calculate entry price based on Fair Value Gap (FVG).
        If no FVG is provided or valid, falls back to fixed offset.
        
        Returns:
            (entry_price, is_valid, message)
        """
        if fvg is not None:
            # Use FVG midpoint as entry
            entry = fvg.midpoint
            
            # Validate FVG entry direction
            is_valid, msg = self.validate_entry_price(entry, market_price, direction)
            
            if is_valid:
                logger.info(f"🎯 FVG Entry Selected: {entry} (Quality: {fvg.quality})")
                return entry, True, f"FVG_ENTRY_RETRACEMENT (Quality: {fvg.quality})"
            else:
                logger.warning(f"FVG at {entry} invalid for {direction}: {msg}. Falling back to fixed offset.")

        # Fallback to legacy fixed offset strategy
        return self.calculate_and_validate(market_price, direction)

    def calculate_and_validate(
        self,
        market_price: float,
        direction: str,
        custom_offset: float = None
    ) -> Tuple[float, bool, str]:
        """
        Calculate entry price and validate it in one call.
        
        Args:
            market_price: Current market price
            direction: "BUY" or "SELL"
            custom_offset: Optional custom offset
        
        Returns:
            (entry_price, is_valid, message)
        
        Example:
            >>> calc = EntryCalculator()
            >>> entry, valid, msg = calc.calculate_and_validate(1.19371, "BUY")
            >>> print(f"{entry}, {valid}, {msg}")
            1.19321, True, "Valid"
        """
        try:
            entry = self.calculate_entry_price(market_price, direction, custom_offset)
            is_valid, message = self.validate_entry_price(entry, market_price, direction)
            return entry, is_valid, message
        except ValueError as e:
            return 0.0, False, str(e)


# Convenience functions for backward compatibility
def calculate_entry_price(
    market_price: float,
    direction: str,
    offset: float = 0.0005
) -> float:
    """
    Calculate entry price (convenience function).
    
    Args:
        market_price: Current market price
        direction: "BUY" or "SELL"
        offset: Distance from market (default 5 pips = 0.0005)
    
    Returns:
        Entry price
    """
    calc = EntryCalculator(offset_pips=offset / 0.0001)
    return calc.calculate_entry_price(market_price, direction)


def validate_entry_price(
    entry: float,
    market_price: float,
    direction: str
) -> Tuple[bool, str]:
    """
    Validate entry price (convenience function).
    
    Args:
        entry: Proposed entry price
        market_price: Current market price
        direction: "BUY" or "SELL"
    
    Returns:
        (is_valid, error_message)
    """
    calc = EntryCalculator()
    return calc.validate_entry_price(entry, market_price, direction)
