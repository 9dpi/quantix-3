"""
Structure State Resolution - Final reasoning logic
Converts evidence scores into market state with confidence

Principle: Relative dominance, not absolute thresholds
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from backend.quantix_core.engine.primitives.fvg_detector import FairValueGap
from backend.quantix_core.engine.primitives.liquidity_filter import LiquiditySweep


@dataclass
class StructureState:
    """
    Final structure state output.
    
    This is what the reasoning engine produces.
    """
    state: str  # "bullish", "bearish", "range", "unclear"
    confidence: float  # 0.0 to 1.0 (Consistency of evidence)
    strength: float    # 0.0 to 1.0 (Force/Momentum of the move)
    dominance: Dict[str, float]  # {"bullish": X, "bearish": Y}
    evidence: List[str]  # Human-readable evidence
    
    # Metadata
    trace_id: str
    source: str
    timeframe: str
    
    # SMC Metadata
    fvgs: List[FairValueGap] = field(default_factory=list)
    sweeps: List[LiquiditySweep] = field(default_factory=list)
    nearest_fvg: Optional[FairValueGap] = None


class StateResolver:
    """
    Resolves final market structure state from evidence scores.
    
    Uses relative dominance, not fixed thresholds.
    This is more robust and explainable.
    """
    
    def __init__(self):
        # Minimum total score to have any opinion
        self.min_total_score = 0.3
        
        # Dominance ratio for clear state (2:1 ratio)
        self.clear_dominance_ratio = 2.0
    
    def resolve_state(
        self,
        bullish_score: float,
        bearish_score: float,
        evidence_items: List[str],
        trace_id: str,
        source: str = "oanda",
        timeframe: str = "H4",
        fvgs: List[FairValueGap] = None,
        sweeps: List[LiquiditySweep] = None,
        nearest_fvg: Optional[FairValueGap] = None
    ) -> StructureState:
        """
        Resolve final structure state from directional scores.
        
        Logic:
        1. If total score too low → "unclear"
        2. If one direction dominates → that direction
        3. If close → "range"
        
        Confidence = |bullish - bearish| / (bullish + bearish)
        """
        total_score = bullish_score + bearish_score
        
        fvgs = fvgs or []
        sweeps = sweeps or []

        # Case 1: Insufficient evidence
        if total_score < self.min_total_score:
            return StructureState(
                state="unclear",
                confidence=0.0,
                strength=0.0,
                dominance={
                    "bullish": bullish_score,
                    "bearish": bearish_score
                },
                evidence=evidence_items or ["Insufficient structure evidence"],
                fvgs=fvgs,
                sweeps=sweeps,
                nearest_fvg=nearest_fvg,
                trace_id=trace_id,
                source=source,
                timeframe=timeframe
            )
        
        # Calculate confidence (consistency of evidence)
        # Higher when one direction dominates
        confidence = abs(bullish_score - bearish_score) / total_score if total_score > 0 else 0.0
        
        # Calculate strength (Force/Momentum)
        # We'll take the average strength of the evidence items as a proxy for 'force'
        # In a more advanced version, this could come from a separate MomentumEngine
        strength = self._calculate_aggregate_strength(evidence_items)

        # Determine state based on relative dominance
        state, final_evidence = self._determine_state(
            bullish_score,
            bearish_score,
            evidence_items,
            confidence
        )
        
        return StructureState(
            state=state,
            confidence=round(confidence, 2),
            strength=round(strength, 2),
            dominance={
                "bullish": round(bullish_score, 2),
                "bearish": round(bearish_score, 2)
            },
            evidence=final_evidence,
            fvgs=fvgs,
            sweeps=sweeps,
            nearest_fvg=nearest_fvg,
            trace_id=trace_id,
            source=source,
            timeframe=timeframe
        )

    def _calculate_aggregate_strength(self, evidence_items: List[str]) -> float:
        """
        Estimate aggregate strength from evidence descriptions.
        (Temporary shim until we pass raw StructureEvidence objects here)
        """
        if not evidence_items:
            return 0.0
            
        strengths = []
        for item in evidence_items:
            # Look for body percentage in description "body 85%"
            if "body " in item:
                try:
                    pct_str = item.split("body ")[1].split("%")[0]
                    strengths.append(int(pct_str) / 100.0)
                except:
                    continue
        
        return sum(strengths) / len(strengths) if strengths else 0.5
    
    def _determine_state(
        self,
        bullish_score: float,
        bearish_score: float,
        evidence_items: List[str],
        confidence: float
    ) -> Tuple[str, List[str]]:
        """
        Determine state based on score dominance.
        
        Returns:
            (state, filtered_evidence)
        """
        # Calculate dominance ratio
        if bearish_score > 0:
            bull_bear_ratio = bullish_score / bearish_score
        else:
            bull_bear_ratio = float('inf') if bullish_score > 0 else 1.0
        
        if bullish_score > 0:
            bear_bull_ratio = bearish_score / bullish_score
        else:
            bear_bull_ratio = float('inf') if bearish_score > 0 else 1.0
        
        # Decision logic
        if bull_bear_ratio >= self.clear_dominance_ratio:
            # Clear bullish dominance
            state = "bullish"
            # Filter to bullish evidence only
            filtered_evidence = [e for e in evidence_items if "bullish" in e.lower() or "BOS" in e]
            
        elif bear_bull_ratio >= self.clear_dominance_ratio:
            # Clear bearish dominance
            state = "bearish"
            filtered_evidence = [e for e in evidence_items if "bearish" in e.lower() or "BOS" in e]
            
        elif bullish_score > bearish_score * 1.2:
            # Moderate bullish lean
            state = "bullish"
            filtered_evidence = evidence_items
            
        elif bearish_score > bullish_score * 1.2:
            # Moderate bearish lean
            state = "bearish"
            filtered_evidence = evidence_items
            
        else:
            # Too close to call → range/neutral
            state = "range"
            filtered_evidence = evidence_items + [
                f"Conflicting signals (bull: {bullish_score:.2f}, bear: {bearish_score:.2f})"
            ]
        
        # Ensure we have at least some evidence
        if not filtered_evidence:
            filtered_evidence = ["No clear structure pattern"]
        
        return state, filtered_evidence
    
    def to_api_format(self, state: StructureState) -> Dict:
        """
        Convert StructureState to API response format.
        
        This matches the frontend's expected format.
        """
        return {
            "feature": "structure",
            "state": state.state,
            "confidence": round(state.confidence, 2),
            "strength": round(state.strength, 2),
            "dominance": state.dominance,
            "evidence": state.evidence,
            "trace_id": state.trace_id,
            "source": state.source,
            "timeframe": state.timeframe
        }
