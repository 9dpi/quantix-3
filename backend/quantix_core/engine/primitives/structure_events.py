"""
Structure Event Detection - BOS (Break of Structure) & CHoCH (Change of Character)
Production-grade implementation with trend context

Principle: Deterministic, explainable, no ML
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

from backend.quantix_core.engine.primitives.swing_detector import SwingPoint


@dataclass
class StructureEvent:
    """
    Represents a structure break event (BOS or CHoCH).
    
    Attributes:
        type: "BOS" (continuation) or "CHoCH" (reversal)
        direction: "Bullish" or "Bearish"
        broken_level: Price level that was broken
        candle_index: Index where break occurred
        body_strength: Body percentage of break candle
        close_acceptance: Whether close is beyond the level (not just wick)
    """
    type: str  # "BOS" or "CHoCH"
    direction: str  # "Bullish" or "Bearish"
    broken_level: float
    candle_index: int
    body_strength: float  # 0.0 to 1.0
    close_acceptance: bool


class StructureEventDetector:
    """
    Detects BOS and CHoCH events based on swing breaks.
    
    BOS = Break in trend direction (continuation)
    CHoCH = Break against trend (reversal signal)
    """
    
    def __init__(self):
        self.break_threshold = 0.0001  # 0.01% minimum break to avoid noise
    
    def detect_events(
        self, 
        df: pd.DataFrame, 
        swings: List[SwingPoint]
    ) -> List[StructureEvent]:
        """
        Detect all structure events (BOS/CHoCH) in the dataset.
        
        Args:
            df: OHLC DataFrame
            swings: List of detected swing points
            
        Returns:
            List of StructureEvent objects
        """
        if len(swings) < 2:
            return []
        
        events = []
        
        # Determine current trend context
        trend = self._determine_trend(swings)
        
        # Check for breaks of recent swings
        recent_swings = swings[-10:]  # Look at last 10 swings
        
        for i in range(len(df)):
            candle_high = df['high'].iloc[i]
            candle_low = df['low'].iloc[i]
            candle_close = df['close'].iloc[i]
            
            # Check if this candle breaks any swing
            for swing in recent_swings:
                if swing.index >= i:
                    continue  # Can't break future swings
                
                event = self._check_swing_break(
                    swing, 
                    candle_high, 
                    candle_low, 
                    candle_close,
                    i,
                    df,
                    trend
                )
                
                if event:
                    events.append(event)
        
        return events
    
    def _determine_trend(self, swings: List[SwingPoint]) -> str:
        """
        Determine trend from last two swings.
        
        Logic:
        - HH + HL = Uptrend
        - LL + LH = Downtrend
        - Mixed = Ranging
        
        Returns:
            "uptrend", "downtrend", or "ranging"
        """
        if len(swings) < 4:
            return "ranging"
        
        # Get last 4 swings (2 highs, 2 lows)
        recent = swings[-4:]
        
        highs = [s for s in recent if s.type == "HIGH"]
        lows = [s for s in recent if s.type == "LOW"]
        
        if len(highs) < 2 or len(lows) < 2:
            return "ranging"
        
        # Check for Higher Highs and Higher Lows
        higher_high = highs[-1].price > highs[-2].price
        higher_low = lows[-1].price > lows[-2].price
        
        # Check for Lower Lows and Lower Highs
        lower_low = lows[-1].price < lows[-2].price
        lower_high = highs[-1].price < highs[-2].price
        
        if higher_high and higher_low:
            return "uptrend"
        elif lower_low and lower_high:
            return "downtrend"
        else:
            return "ranging"
    
    def _check_swing_break(
        self,
        swing: SwingPoint,
        candle_high: float,
        candle_low: float,
        candle_close: float,
        candle_index: int,
        df: pd.DataFrame,
        trend: str
    ) -> Optional[StructureEvent]:
        """
        Check if current candle breaks a swing point.
        
        Returns:
            StructureEvent if break detected, None otherwise
        """
        candle_open = df['open'].iloc[candle_index]
        
        # Calculate body strength
        body = abs(candle_close - candle_open)
        total_range = candle_high - candle_low
        body_strength = body / total_range if total_range > 0 else 0
        
        # Check bullish break (swing high broken)
        if swing.type == "HIGH":
            if candle_close > swing.price * (1 + self.break_threshold):
                # Close above swing high = acceptance
                close_acceptance = True
                
                # Determine if BOS or CHoCH
                if trend == "uptrend":
                    event_type = "BOS"  # Breaking high in uptrend = continuation
                else:
                    event_type = "CHoCH"  # Breaking high in downtrend = reversal
                
                return StructureEvent(
                    type=event_type,
                    direction="Bullish",
                    broken_level=swing.price,
                    candle_index=candle_index,
                    body_strength=body_strength,
                    close_acceptance=close_acceptance
                )
            elif candle_high > swing.price * (1 + self.break_threshold):
                # Wick break but close below = weak/potential fake
                close_acceptance = False
                
                if trend == "uptrend":
                    event_type = "BOS"
                else:
                    event_type = "CHoCH"
                
                return StructureEvent(
                    type=event_type,
                    direction="Bullish",
                    broken_level=swing.price,
                    candle_index=candle_index,
                    body_strength=body_strength,
                    close_acceptance=close_acceptance
                )
        
        # Check bearish break (swing low broken)
        elif swing.type == "LOW":
            if candle_close < swing.price * (1 - self.break_threshold):
                close_acceptance = True
                
                if trend == "downtrend":
                    event_type = "BOS"  # Breaking low in downtrend = continuation
                else:
                    event_type = "CHoCH"  # Breaking low in uptrend = reversal
                
                return StructureEvent(
                    type=event_type,
                    direction="Bearish",
                    broken_level=swing.price,
                    candle_index=candle_index,
                    body_strength=body_strength,
                    close_acceptance=close_acceptance
                )
            elif candle_low < swing.price * (1 - self.break_threshold):
                close_acceptance = False
                
                if trend == "downtrend":
                    event_type = "BOS"
                else:
                    event_type = "CHoCH"
                
                return StructureEvent(
                    type=event_type,
                    direction="Bearish",
                    broken_level=swing.price,
                    candle_index=candle_index,
                    body_strength=body_strength,
                    close_acceptance=close_acceptance
                )
        
        return None
    
    def get_most_recent_event(self, events: List[StructureEvent]) -> Optional[StructureEvent]:
        """Get the most recent structure event"""
        return events[-1] if events else None
