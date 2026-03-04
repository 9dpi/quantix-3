"""
Fair Value Gap (FVG) Detector — Quantix SMC-Lite M15
=====================================================
Detects price imbalances (Fair Value Gaps) in OHLCV data.

An FVG occurs when three consecutive candles create a price gap
where the wick of candle[0] does NOT overlap the wick of candle[2].
This gap represents an area of "unfair" pricing that the market
tends to revisit (fill), making it an ideal entry zone.

Principle: Deterministic, explainable, no ML
Version: 1.0
"""

import pandas as pd
import numpy as np
from typing import List, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class FairValueGap:
    """
    Represents a single Fair Value Gap.

    Attributes:
        index: Index of the middle candle (the "impulse" candle)
        type: "BULLISH" or "BEARISH"
        top: Upper boundary of the gap
        bottom: Lower boundary of the gap
        midpoint: (top + bottom) / 2 — optimal entry point
        size_pips: Gap size in pips (for EURUSD, 1 pip = 0.0001)
        filled: Whether price has returned to fill this gap
        quality: Gap quality score (0.0 - 1.0)
        candle_strength: Body ratio of the impulse candle
    """
    index: int
    type: str               # "BULLISH" or "BEARISH"
    top: float
    bottom: float
    midpoint: float
    size_pips: float
    filled: bool = False
    quality: float = 0.0
    candle_strength: float = 0.0


class FVGDetector:
    """
    Detects Fair Value Gaps (FVGs) in M15 OHLCV data.

    FVG Logic:
    - Bullish FVG: candle[i].high < candle[i+2].low
      (Gap below current price — price may dip to fill it → BUY zone)
    - Bearish FVG: candle[i].low > candle[i+2].high
      (Gap above current price — price may rally to fill it → SELL zone)

    The middle candle (candle[i+1]) is the "impulse" that created the gap.
    """

    def __init__(
        self,
        min_gap_pips: float = 1.0,
        max_gap_pips: float = 30.0,
        max_age_candles: int = 50,
        pip_value: float = 0.0001
    ):
        """
        Initialize FVG Detector.

        Args:
            min_gap_pips: Minimum gap size to consider (filter noise)
            max_gap_pips: Maximum gap size to consider (filter anomalies)
            max_age_candles: Only consider FVGs within this many candles
            pip_value: Value of 1 pip (0.0001 for EURUSD)
        """
        self.min_gap = min_gap_pips * pip_value
        self.max_gap = max_gap_pips * pip_value
        self.max_age = max_age_candles
        self.pip_value = pip_value

        logger.debug(
            f"FVGDetector initialized: "
            f"min={min_gap_pips}p, max={max_gap_pips}p, age={max_age_candles}"
        )

    def detect_fvgs(self, df: pd.DataFrame) -> List[FairValueGap]:
        """
        Scan the entire DataFrame for Fair Value Gaps.

        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns

        Returns:
            List of FairValueGap objects, sorted by index (newest last)
        """
        if len(df) < 3:
            return []

        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values
        opens = df['open'].astype(float).values
        closes = df['close'].astype(float).values

        fvgs: List[FairValueGap] = []
        start_idx = max(0, len(df) - self.max_age - 2)

        for i in range(start_idx, len(df) - 2):
            # --- Bullish FVG ---
            # Candle[i] high < Candle[i+2] low → gap below
            gap_bottom = highs[i]
            gap_top = lows[i + 2]

            if gap_top > gap_bottom:
                size = gap_top - gap_bottom

                if self.min_gap <= size <= self.max_gap:
                    # Quality = impulse candle body ratio × gap size factor
                    impulse_body = abs(closes[i + 1] - opens[i + 1])
                    impulse_range = highs[i + 1] - lows[i + 1]
                    body_ratio = (impulse_body / impulse_range) if impulse_range > 0 else 0

                    # Larger, cleaner gaps = higher quality
                    size_score = min(1.0, (size / self.pip_value) / 10.0)
                    quality = round((body_ratio * 0.6) + (size_score * 0.4), 4)

                    fvg = FairValueGap(
                        index=i + 1,
                        type="BULLISH",
                        top=round(gap_top, 5),
                        bottom=round(gap_bottom, 5),
                        midpoint=round((gap_top + gap_bottom) / 2, 5),
                        size_pips=round(size / self.pip_value, 1),
                        quality=quality,
                        candle_strength=round(body_ratio, 4)
                    )
                    fvgs.append(fvg)

            # --- Bearish FVG ---
            # Candle[i] low > Candle[i+2] high → gap above
            gap_top_bear = lows[i]
            gap_bottom_bear = highs[i + 2]

            if gap_top_bear > gap_bottom_bear:
                size = gap_top_bear - gap_bottom_bear

                if self.min_gap <= size <= self.max_gap:
                    impulse_body = abs(closes[i + 1] - opens[i + 1])
                    impulse_range = highs[i + 1] - lows[i + 1]
                    body_ratio = (impulse_body / impulse_range) if impulse_range > 0 else 0

                    size_score = min(1.0, (size / self.pip_value) / 10.0)
                    quality = round((body_ratio * 0.6) + (size_score * 0.4), 4)

                    fvg = FairValueGap(
                        index=i + 1,
                        type="BEARISH",
                        top=round(gap_top_bear, 5),
                        bottom=round(gap_bottom_bear, 5),
                        midpoint=round((gap_top_bear + gap_bottom_bear) / 2, 5),
                        size_pips=round(size / self.pip_value, 1),
                        quality=quality,
                        candle_strength=round(body_ratio, 4)
                    )
                    fvgs.append(fvg)

        # Mark filled FVGs
        fvgs = self._mark_filled(fvgs, df)

        logger.info(
            f"FVG Scan complete: {len(fvgs)} total, "
            f"{sum(1 for f in fvgs if not f.filled)} unfilled"
        )

        return fvgs

    def _mark_filled(
        self,
        fvgs: List[FairValueGap],
        df: pd.DataFrame
    ) -> List[FairValueGap]:
        """
        Check if subsequent candles have filled (touched) each FVG.

        A Bullish FVG is "filled" if any candle after it has a low <= midpoint.
        A Bearish FVG is "filled" if any candle after it has a high >= midpoint.
        """
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        for fvg in fvgs:
            # Check all candles after the FVG
            for j in range(fvg.index + 2, len(df)):
                if fvg.type == "BULLISH":
                    # Price dipped into the gap = filled
                    if lows[j] <= fvg.midpoint:
                        fvg.filled = True
                        break
                elif fvg.type == "BEARISH":
                    # Price rallied into the gap = filled
                    if highs[j] >= fvg.midpoint:
                        fvg.filled = True
                        break

        return fvgs

    def get_unfilled(self, fvgs: List[FairValueGap]) -> List[FairValueGap]:
        """
        Return only unfilled FVGs (potential entry zones).

        Args:
            fvgs: List of all detected FVGs

        Returns:
            List of unfilled FVGs, sorted by recency (newest first)
        """
        unfilled = [f for f in fvgs if not f.filled]
        unfilled.sort(key=lambda x: x.index, reverse=True)
        return unfilled

    def get_nearest_entry_fvg(
        self,
        fvgs: List[FairValueGap],
        direction: str,
        current_price: float,
        max_distance_pips: float = 20.0
    ) -> Optional[FairValueGap]:
        """
        Find the nearest unfilled FVG suitable for entry.

        For BUY signals: Find the nearest BULLISH FVG below current price.
        For SELL signals: Find the nearest BEARISH FVG above current price.

        Args:
            fvgs: List of all detected FVGs
            direction: "BUY" or "SELL"
            current_price: Current market price
            max_distance_pips: Maximum distance from price to consider

        Returns:
            Best FVG for entry, or None if no suitable FVG found
        """
        max_distance = max_distance_pips * self.pip_value
        unfilled = self.get_unfilled(fvgs)

        candidates: List[FairValueGap] = []

        for fvg in unfilled:
            if direction == "BUY" and fvg.type == "BULLISH":
                # Bullish FVG must be BELOW current price (buy the dip)
                distance = current_price - fvg.midpoint
                if 0 < distance <= max_distance:
                    candidates.append(fvg)

            elif direction == "SELL" and fvg.type == "BEARISH":
                # Bearish FVG must be ABOVE current price (sell the rally)
                distance = fvg.midpoint - current_price
                if 0 < distance <= max_distance:
                    candidates.append(fvg)

        if not candidates:
            logger.debug(
                f"No suitable {direction} FVG found within "
                f"{max_distance_pips} pips of {current_price}"
            )
            return None

        # Sort by quality (highest first), then by proximity (closest first)
        candidates.sort(key=lambda f: (-f.quality, abs(f.midpoint - current_price)))

        best = candidates[0]
        dist_pips = abs(best.midpoint - current_price) / self.pip_value

        logger.info(
            f"🎯 Best FVG for {direction}: "
            f"midpoint={best.midpoint}, quality={best.quality:.2f}, "
            f"distance={dist_pips:.1f}p, size={best.size_pips:.1f}p"
        )

        return best

    def get_fvg_summary(self, fvgs: List[FairValueGap]) -> dict:
        """
        Generate a summary of all detected FVGs for telemetry/logging.

        Returns:
            Dictionary with FVG statistics
        """
        bullish = [f for f in fvgs if f.type == "BULLISH"]
        bearish = [f for f in fvgs if f.type == "BEARISH"]
        unfilled = [f for f in fvgs if not f.filled]

        return {
            "total": len(fvgs),
            "bullish": len(bullish),
            "bearish": len(bearish),
            "unfilled": len(unfilled),
            "avg_quality": round(
                sum(f.quality for f in fvgs) / len(fvgs), 4
            ) if fvgs else 0.0,
            "avg_size_pips": round(
                sum(f.size_pips for f in fvgs) / len(fvgs), 1
            ) if fvgs else 0.0,
        }
