"""
Liquidity Sweep Filter — Quantix SMC-Lite M15
============================================
Detects "Liquidity Sweeps" or "Stop Hunts" in market structure.

A Liquidity Sweep occurs when price moves beyond a recent swing point 
(high or low) but fails to close beyond it, instead rejecting 
sharply with a long wick. This indicates "smart money" grabbing 
liquidity before a potential reversal.

Principle: Deterministic, explainable, no ML
Version: 1.0
"""

import pandas as pd
from typing import List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from backend.quantix_core.engine.primitives.swing_detector import SwingPoint


@dataclass
class LiquiditySweep:
    """
    Represents a detected liquidity sweep event.

    Attributes:
        index: Index of the candle that performed the sweep
        swept_level: Price level of the swing point that was swept
        type: "BULLISH_SWEEP" (swept a low) or "BEARISH_SWEEP" (swept a high)
        rejection_strength: Ratio of wick length to total range (0.0 - 1.0)
        wick_size_pips: Length of the piercing wick in pips
        swing_index: Original index of the swept swing point
    """
    index: int
    swept_level: float
    type: str               # "BULLISH_SWEEP" or "BEARISH_SWEEP"
    rejection_strength: float
    wick_size_pips: float
    swing_index: int


class LiquidityFilter:
    """
    Detects and filters liquidity sweep events in OHLCV data.
    
    Logic:
    - BEARISH SWEEP: Price goes ABOVE a swing high but closes BELOW it.
    - BULLISH SWEEP: Price goes BELOW a swing low but closes ABOVE it.
    """

    def __init__(self, wick_threshold_pips: float = 0.5, pip_value: float = 0.0001):
        """
        Initialize Liquidity Filter.

        Args:
            wick_threshold_pips: Minimum wick penetration to count as a sweep
            pip_value: Value of 1 pip (0.0001 for EURUSD)
        """
        self.wick_threshold = wick_threshold_pips * pip_value
        self.pip_value = pip_value

    def detect_sweeps(
        self, 
        df: pd.DataFrame, 
        swings: List[SwingPoint],
        max_lookback_swings: int = 10
    ) -> List[LiquiditySweep]:
        """
        Detect liquidity sweeps of recent swing points.

        Args:
            df: OHLCV DataFrame
            swings: List of detected swing points
            max_lookback_swings: How many recent swings to check

        Returns:
            List of LiquiditySweep objects
        """
        if len(swings) < 1 or len(df) < 2:
            return []

        sweeps = []
        recent_swings = swings[-max_lookback_swings:]
        
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values

        # Current candle being analyzed (usually the last or second to last)
        current_idx = len(df) - 1
        
        candle_high = highs[current_idx]
        candle_low = lows[current_idx]
        candle_close = closes[current_idx]
        candle_open = opens[current_idx]
        
        total_range = candle_high - candle_low
        if total_range == 0:
            return []

        for swing in recent_swings:
            # Cannot sweep a future swing or a swing at the same index
            if swing.index >= current_idx:
                continue
                
            # --- BEARISH SWEEP (Swept a HIGH) ---
            if swing.type == "HIGH":
                # Pierced high but closed below
                if candle_high > swing.price and candle_close <= swing.price:
                    wick_size = candle_high - max(candle_open, candle_close)
                    
                    if wick_size >= self.wick_threshold:
                        # Rejection strength = wick vs total range
                        strength = wick_size / total_range
                        
                        sweeps.append(LiquiditySweep(
                            index=current_idx,
                            swept_level=swing.price,
                            type="BEARISH_SWEEP",
                            rejection_strength=round(strength, 4),
                            wick_size_pips=round(wick_size / self.pip_value, 2),
                            swing_index=swing.index
                        ))

            # --- BULLISH SWEEP (Swept a LOW) ---
            elif swing.type == "LOW":
                # Pierced low but closed above
                if candle_low < swing.price and candle_close >= swing.price:
                    wick_size = min(candle_open, candle_close) - candle_low
                    
                    if wick_size >= self.wick_threshold:
                        strength = wick_size / total_range
                        
                        sweeps.append(LiquiditySweep(
                            index=current_idx,
                            swept_level=swing.price,
                            type="BULLISH_SWEEP",
                            rejection_strength=round(strength, 4),
                            wick_size_pips=round(wick_size / self.pip_value, 2),
                            swing_index=swing.index
                        ))

        if sweeps:
            logger.info(f"🛸 Detected {len(sweeps)} Liquidity Sweeps in current candle")
            for s in sweeps:
                logger.debug(f"  {s.type}: level={s.swept_level}, strength={s.rejection_strength}")

        return sweeps

    def has_active_sweep(self, sweeps: List[LiquiditySweep], direction: str) -> bool:
        """
        Check if there is a sweep in a specific direction.

        Args:
            sweeps: List of detected sweeps
            direction: "BUY" (looks for bullish sweep) or "SELL" (looks for bearish sweep)
        """
        target_type = "BULLISH_SWEEP" if direction == "BUY" else "BEARISH_SWEEP"
        return any(s.type == target_type for s in sweeps)
