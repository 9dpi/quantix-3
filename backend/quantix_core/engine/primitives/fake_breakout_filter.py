"""
Fake Breakout Filter - Production-grade quality gate
Prevents AI from making retail-level mistakes

Principle: Better to miss a trade than take a fake breakout
"""

import pandas as pd
from typing import List

from backend.quantix_core.engine.primitives.structure_events import StructureEvent


class FakeBreakoutFilter:
    """
    Filters out fake breakouts using deterministic criteria.
    
    Fake breakout = break that immediately reverses.
    This is what kills retail traders.
    """
    
    def __init__(self):
        # Thresholds (tunable but deterministic)
        self.wick_threshold = 0.6  # Wick > 60% of total range = suspicious
        self.weak_body_threshold = 0.3  # Body < 30% = weak conviction
        self.followthrough_candles = 2  # Need 2 candles to confirm
    
    def is_fake_breakout(
        self, 
        event: StructureEvent, 
        df: pd.DataFrame
    ) -> bool:
        """
        Determine if a structure event is a fake breakout.
        
        Fake if >= 2 of these conditions are true:
        1. Close rejected back into range
        2. Wick dominant (>60% of candle)
        3. Weak body (<30%)
        4. No follow-through in next candles
        
        Args:
            event: StructureEvent to check
            df: OHLC DataFrame
            
        Returns:
            True if fake breakout detected
        """
        fake_score = 0
        
        # Get the break candle
        if event.candle_index >= len(df):
            return False
        
        candle = df.iloc[event.candle_index]
        
        # Criterion 1: Close rejected?
        if not event.close_acceptance:
            fake_score += 1
        
        # Criterion 2: Wick dominant?
        if self._is_wick_dominant(candle):
            fake_score += 1
        
        # Criterion 3: Weak body?
        if event.body_strength < self.weak_body_threshold:
            fake_score += 1
        
        # Criterion 4: No follow-through?
        if not self._has_followthrough(event, df):
            fake_score += 1
        
        # Fake if 2 or more criteria met
        return fake_score >= 2
    
    def _is_wick_dominant(self, candle: pd.Series) -> bool:
        """
        Check if wick is dominant (>60% of total range).
        
        Wick-dominant candles show rejection, not acceptance.
        """
        high = candle['high']
        low = candle['low']
        open_price = candle['open']
        close = candle['close']
        
        total_range = high - low
        if total_range == 0:
            return False
        
        # Calculate total wick length
        upper_wick = high - max(open_price, close)
        lower_wick = min(open_price, close) - low
        total_wick = upper_wick + lower_wick
        
        wick_ratio = total_wick / total_range
        
        return wick_ratio > self.wick_threshold
    
    def _has_followthrough(
        self, 
        event: StructureEvent, 
        df: pd.DataFrame
    ) -> bool:
        """
        Check if break has follow-through in subsequent candles.
        
        Real breakouts continue in the break direction.
        Fake breakouts reverse immediately.
        """
        start_idx = event.candle_index + 1
        end_idx = min(start_idx + self.followthrough_candles, len(df))
        
        if start_idx >= len(df):
            return False  # No candles after break
        
        followthrough_candles = df.iloc[start_idx:end_idx]
        
        if len(followthrough_candles) == 0:
            return False
        
        # Check if subsequent candles continue beyond broken level
        if event.direction == "Bullish":
            # For bullish break, check if closes stay above broken level
            closes_above = (followthrough_candles['close'] > event.broken_level).sum()
            return closes_above >= len(followthrough_candles) * 0.5  # At least 50%
        else:
            # For bearish break, check if closes stay below broken level
            closes_below = (followthrough_candles['close'] < event.broken_level).sum()
            return closes_below >= len(followthrough_candles) * 0.5
    
    def filter_events(
        self, 
        events: List[StructureEvent], 
        df: pd.DataFrame
    ) -> tuple[List[StructureEvent], List[StructureEvent]]:
        """
        Filter events into valid and fake breakouts.
        
        Returns:
            (valid_events, fake_events)
        """
        valid = []
        fake = []
        
        for event in events:
            if self.is_fake_breakout(event, df):
                fake.append(event)
            else:
                valid.append(event)
        
        return valid, fake
