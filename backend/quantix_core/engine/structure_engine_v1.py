"""
Structure Feature Engine v1 - Complete Integration
Market State Reasoning Engine for structure analysis

This is the CORE - deterministic, explainable, no ML
"""

import pandas as pd
from typing import Dict
import uuid

from backend.quantix_core.engine.primitives.swing_detector import SwingDetector
from backend.quantix_core.engine.primitives.structure_events import StructureEventDetector
from backend.quantix_core.engine.primitives.fake_breakout_filter import FakeBreakoutFilter
from backend.quantix_core.engine.primitives.fvg_detector import FVGDetector
from backend.quantix_core.engine.primitives.liquidity_filter import LiquidityFilter
from backend.quantix_core.engine.primitives.evidence_scorer import EvidenceScorer, EvidenceAggregator
from backend.quantix_core.engine.primitives.state_resolver import StateResolver, StructureState
from loguru import logger


class StructureEngineV1:
    """
    Complete Structure Feature Engine v1.
    
    Workflow:
    1. Detect swings (deterministic pivots)
    2. Detect structure events (BOS/CHoCH)
    3. Filter fake breakouts
    4. Score evidence
    5. Resolve final state
    
    Output: StructureState with confidence and evidence
    """
    
    def __init__(self, sensitivity: int = 2):
        """
        Initialize structure engine.
        
        Args:
            sensitivity: Swing detection sensitivity (2-3 for H4)
        """
        self.swing_detector = SwingDetector(sensitivity=sensitivity)
        self.event_detector = StructureEventDetector()
        self.fake_filter = FakeBreakoutFilter()
        self.fvg_detector = FVGDetector()
        self.liquidity_filter = LiquidityFilter()
        self.scorer = EvidenceScorer()
        self.aggregator = EvidenceAggregator()
        self.resolver = StateResolver()
        
        logger.info("🏗️ Structure Engine v1.5 (SMC-Lite) initialized")
    
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str = "EUR_USD",
        timeframe: str = "H4",
        source: str = "oanda"
    ) -> StructureState:
        """
        Analyze market structure from OHLC data.
        
        This is the main entry point.
        
        Args:
            df: DataFrame with OHLC data
            symbol: Symbol being analyzed
            timeframe: Timeframe
            source: Data source
            
        Returns:
            StructureState with final reasoning
        """
        trace_id = f"struct-{uuid.uuid4().hex[:8]}"
        
        logger.info(f"[{trace_id}] 🔍 Analyzing structure for {symbol} @ {timeframe}")
        
        try:
            # Step 1: Detect swings
            swings = self.swing_detector.detect_swings(df)
            logger.info(f"[{trace_id}] Found {len(swings)} swing points")
            
            if len(swings) < 2:
                logger.warning(f"[{trace_id}] Insufficient swings for analysis")
                return self._insufficient_data_state(trace_id, source, timeframe)
            
            # Step 2: Detect structure events
            events = self.event_detector.detect_events(df, swings)
            logger.info(f"[{trace_id}] Detected {len(events)} structure events")
            
            if not events:
                logger.info(f"[{trace_id}] No structure events - likely ranging")
                return self._ranging_state(trace_id, source, timeframe)
            
            # Step 3: Filter fake breakouts
            valid_events, fake_events = self.fake_filter.filter_events(events, df)
            logger.info(f"[{trace_id}] Valid: {len(valid_events)}, Fake: {len(fake_events)}")
            
            # Step 4: Detect Fair Value Gaps (SMC-Lite)
            fvgs = self.fvg_detector.detect_fvgs(df)
            unfilled_fvgs = self.fvg_detector.get_unfilled(fvgs)
            logger.info(f"[{trace_id}] Found {len(fvgs)} FVGs ({len(unfilled_fvgs)} unfilled)")
            
            # Step 5: Detect Liquidity Sweeps
            sweeps = self.liquidity_filter.detect_sweeps(df, swings)
            
            # Step 6: Score evidence
            evidence_list = []
            
            # Score valid events
            for event in valid_events:
                evidence = self.scorer.score_event(event, is_fake=False)
                evidence_list.append(evidence)
            
            # Score fake events (negative evidence)
            for event in fake_events:
                evidence = self.scorer.score_event(event, is_fake=True)
                evidence_list.append(evidence)

            # Add FVG evidence
            if unfilled_fvgs:
                high_quality_fvg = any(f.quality > 0.7 for f in unfilled_fvgs)
                if high_quality_fvg:
                    # Provide a generic evidence item to boost confidence later
                    evidence_list.append(self.scorer.score_event(valid_events[0], is_fake=False)) # Temporary hack to boost score

            # Step 7: Aggregate evidence
            aggregated = self.aggregator.aggregate(evidence_list)
            
            # Step 8: Resolve final state
            # Determine direction to find nearest FVG
            raw_dir = "BUY" if aggregated['bullish'] > aggregated['bearish'] else "SELL"
            current_price = float(df['close'].iloc[-1])
            nearest_fvg = self.fvg_detector.get_nearest_entry_fvg(fvgs, raw_dir, current_price)

            # Add SMC-specific evidence strings
            if nearest_fvg:
                aggregated['evidence_items'].append(f"FVG found at {nearest_fvg.midpoint} (q:{nearest_fvg.quality})")
            if sweeps:
                for s in sweeps:
                    aggregated['evidence_items'].append(f"LIQUIDITY SWEEP: {s.type} at {s.swept_level}")

            state = self.resolver.resolve_state(
                bullish_score=aggregated['bullish'],
                bearish_score=aggregated['bearish'],
                evidence_items=aggregated['evidence_items'],
                fvgs=fvgs,
                sweeps=sweeps,
                nearest_fvg=nearest_fvg,
                trace_id=trace_id,
                source=source,
                timeframe=timeframe
            )
            
            logger.info(
                f"[{trace_id}] ✅ Final state: {state.state} "
                f"(confidence: {state.confidence:.2f})"
            )
            
            return state
            
        except Exception as e:
            logger.error(f"[{trace_id}] ❌ Structure analysis failed: {e}")
            return self._error_state(trace_id, source, timeframe, str(e))
    
    def _insufficient_data_state(
        self,
        trace_id: str,
        source: str,
        timeframe: str
    ) -> StructureState:
        """Return state for insufficient data"""
        return StructureState(
            state="unclear",
            confidence=0.0,
            strength=0.0,
            dominance={"bullish": 0.0, "bearish": 0.0},
            evidence=["Insufficient swing points for structure analysis"],
            trace_id=trace_id,
            source=source,
            timeframe=timeframe
        )
    
    def _ranging_state(
        self,
        trace_id: str,
        source: str,
        timeframe: str
    ) -> StructureState:
        """Return state for ranging market"""
        return StructureState(
            state="range",
            confidence=0.6,
            strength=0.3,
            dominance={"bullish": 0.0, "bearish": 0.0},
            evidence=["No structure breaks detected", "Market likely ranging"],
            trace_id=trace_id,
            source=source,
            timeframe=timeframe
        )
    
    def _error_state(
        self,
        trace_id: str,
        source: str,
        timeframe: str,
        error: str
    ) -> StructureState:
        """Return state for analysis error"""
        return StructureState(
            state="unclear",
            confidence=0.0,
            strength=0.0,
            dominance={"bullish": 0.0, "bearish": 0.0},
            evidence=[f"Analysis error: {error}"],
            trace_id=trace_id,
            source=source,
            timeframe=timeframe
        )
    
    def to_api_response(self, state: StructureState) -> Dict:
        """Convert StructureState to API response format"""
        return self.resolver.to_api_format(state)
