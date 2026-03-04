"""
Swing Detection Module - Production-grade
Deterministic swing high/low detection WITHOUT ZigZag

Principle: Auditable, explainable, no repaint
"""

import pandas as pd
import numpy as np
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class SwingPoint:
    """
    Represents a swing high or low point.
    
    Attributes:
        index: Candle index in the dataset
        price: Price level of the swing
        type: "HIGH" or "LOW"
        strength: Number of confirming candles on each side
    """
    index: int
    price: float
    type: str  # "HIGH" or "LOW"
    strength: int  # Confirmation strength


class SwingDetector:
    """
    Detects swing highs and lows using deterministic logic.
    
    NO ZigZag - uses clean pivot detection instead.
    """
    
    def __init__(self, sensitivity: int = 2):
        """
        Args:
            sensitivity: Number of candles on each side to confirm swing (n)
                        H4 typically uses 2-3
        """
        self.sensitivity = sensitivity
    
    def detect_swings(self, df: pd.DataFrame) -> List[SwingPoint]:
        """
        Detect all swing points in the dataset.
        
        Args:
            df: DataFrame with 'high' and 'low' columns
            
        Returns:
            List of SwingPoint objects
        """
        swings = []
        
        # Detect swing highs
        swing_highs = self._detect_swing_highs(df)
        swings.extend(swing_highs)
        
        # Detect swing lows
        swing_lows = self._detect_swing_lows(df)
        swings.extend(swing_lows)
        
        # Sort by index
        swings.sort(key=lambda x: x.index)
        
        return swings
    
    def _detect_swing_highs(self, df: pd.DataFrame) -> List[SwingPoint]:
        """
        Detect swing highs.
        
        Swing High criteria:
        High[i] > High[i-n...i-1] AND High[i] > High[i+1...i+n]
        """
        highs = df['high'].values
        swing_highs = []
        
        n = self.sensitivity
        
        # Can't detect swings at edges
        for i in range(n, len(highs) - n):
            current_high = highs[i]
            
            # Check left side (previous n candles)
            left_valid = all(current_high > highs[i-j] for j in range(1, n+1))
            
            # Check right side (next n candles)
            right_valid = all(current_high > highs[i+j] for j in range(1, n+1))
            
            if left_valid and right_valid:
                # Calculate strength (how many extra candles confirm)
                strength = self._calculate_swing_strength(highs, i, 'high')
                
                swing_highs.append(SwingPoint(
                    index=i,
                    price=current_high,
                    type="HIGH",
                    strength=strength
                ))
        
        return swing_highs
    
    def _detect_swing_lows(self, df: pd.DataFrame) -> List[SwingPoint]:
        """
        Detect swing lows.
        
        Swing Low criteria:
        Low[i] < Low[i-n...i-1] AND Low[i] < Low[i+1...i+n]
        """
        lows = df['low'].values
        swing_lows = []
        
        n = self.sensitivity
        
        for i in range(n, len(lows) - n):
            current_low = lows[i]
            
            # Check left side
            left_valid = all(current_low < lows[i-j] for j in range(1, n+1))
            
            # Check right side
            right_valid = all(current_low < lows[i+j] for j in range(1, n+1))
            
            if left_valid and right_valid:
                strength = self._calculate_swing_strength(lows, i, 'low')
                
                swing_lows.append(SwingPoint(
                    index=i,
                    price=current_low,
                    type="LOW",
                    strength=strength
                ))
        
        return swing_lows
    
    def _calculate_swing_strength(
        self, 
        prices: np.ndarray, 
        index: int, 
        swing_type: str
    ) -> int:
        """
        Calculate swing strength (how clean the swing is).
        
        Strength = number of confirming candles beyond minimum requirement.
        Higher strength = cleaner swing = higher confidence.
        
        Returns:
            Strength value (typically 2-5)
        """
        strength = self.sensitivity  # Start with base requirement
        
        # Check how many additional candles confirm the swing
        max_lookback = min(10, index, len(prices) - index - 1)
        
        if swing_type == 'high':
            # Count additional higher candles
            for offset in range(self.sensitivity + 1, max_lookback + 1):
                if index - offset >= 0 and prices[index] > prices[index - offset]:
                    strength += 0.5
                if index + offset < len(prices) and prices[index] > prices[index + offset]:
                    strength += 0.5
                else:
                    break
        else:  # low
            for offset in range(self.sensitivity + 1, max_lookback + 1):
                if index - offset >= 0 and prices[index] < prices[index - offset]:
                    strength += 0.5
                if index + offset < len(prices) and prices[index] < prices[index + offset]:
                    strength += 0.5
                else:
                    break
        
        return int(strength)
    
    def get_recent_swings(self, swings: List[SwingPoint], count: int = 4) -> List[SwingPoint]:
        """Get the most recent N swings"""
        return swings[-count:] if len(swings) >= count else swings
