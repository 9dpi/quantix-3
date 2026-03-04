"""
Evidence Scoring & Aggregation - Core reasoning logic
Converts structure events into weighted evidence with confidence

Principle: Deterministic, explainable, no ML
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

from backend.quantix_core.engine.primitives.structure_events import StructureEvent
from backend.quantix_core.engine.primitives.swing_detector import SwingPoint


class EvidenceType(str, Enum):
    """Types of structure evidence"""
    BOS = "BOS"
    CHOCH = "CHoCH"
    SWING_BREAK = "SWING_BREAK"
    FAKEOUT_REJECTED = "FAKEOUT_REJECTED"
    SWING_CONTINUATION = "SWING_CONTINUATION"


@dataclass
class StructureEvidence:
    """
    Structured evidence from structure analysis.
    
    Evidence = fact that happened, not prediction.
    """
    type: EvidenceType
    direction: str  # "bullish" or "bearish"
    strength: float  # 0.0 to 1.0 (how strong the signal)
    quality: float  # 0.0 to 1.0 (how clean the execution)
    description: str  # Human-readable evidence
    details: Dict  # Additional context for debugging


class EvidenceScorer:
    """
    Scores structure evidence using deterministic rules.
    
    NO ML - pure logic based on market structure principles.
    """
    
    # Base scores for different evidence types
    BASE_SCORES = {
        EvidenceType.BOS: 0.6,  # Strong continuation signal
        EvidenceType.CHOCH: 0.5,  # Reversal signal
        EvidenceType.SWING_BREAK: 0.4,  # Moderate signal
        EvidenceType.SWING_CONTINUATION: 0.3,  # Weak confirmation
        EvidenceType.FAKEOUT_REJECTED: -0.4  # Negative evidence
    }
    
    def score_event(self, event: StructureEvent, is_fake: bool = False) -> StructureEvidence:
        """
        Score a structure event into weighted evidence.
        
        Args:
            event: StructureEvent from detection
            is_fake: Whether this is a fake breakout
            
        Returns:
            StructureEvidence with score
        """
        if is_fake:
            # Fake breakout = negative evidence
            return StructureEvidence(
                type=EvidenceType.FAKEOUT_REJECTED,
                direction=event.direction.lower(),
                strength=0.8,  # High strength negative
                quality=self._calculate_quality(event),
                description=f"Fake {event.direction.lower()} breakout rejected at {event.broken_level:.5f}",
                details={
                    "broken_level": event.broken_level,
                    "body_strength": event.body_strength,
                    "close_acceptance": event.close_acceptance
                }
            )
        
        # Determine evidence type
        if event.type == "BOS":
            evidence_type = EvidenceType.BOS
        elif event.type == "CHoCH":
            evidence_type = EvidenceType.CHOCH
        else:
            evidence_type = EvidenceType.SWING_BREAK
        
        # Calculate strength and quality
        strength = self._calculate_strength(event)
        quality = self._calculate_quality(event)
        
        # Generate description
        description = self._generate_description(event, evidence_type)
        
        return StructureEvidence(
            type=evidence_type,
            direction=event.direction.lower(),
            strength=strength,
            quality=quality,
            description=description,
            details={
                "broken_level": event.broken_level,
                "body_strength": event.body_strength,
                "close_acceptance": event.close_acceptance,
                "candle_index": event.candle_index
            }
        )
    
    def _calculate_strength(self, event: StructureEvent) -> float:
        """
        Calculate signal strength (0.0 to 1.0).
        
        Based on:
        - Body strength (strong body = strong conviction)
        - Close acceptance (close beyond level = stronger)
        """
        strength = 0.5  # Base
        
        # Body strength contribution (0 to 0.3)
        strength += event.body_strength * 0.3
        
        # Close acceptance bonus (0.2)
        if event.close_acceptance:
            strength += 0.2
        
        return min(1.0, strength)
    
    def _calculate_quality(self, event: StructureEvent) -> float:
        """
        Calculate execution quality (0.0 to 1.0).
        
        Quality = how clean the break was.
        High quality = high confidence.
        """
        quality = 0.7  # Base quality
        
        # Strong body = cleaner execution
        if event.body_strength > 0.7:
            quality += 0.2
        elif event.body_strength < 0.3:
            quality -= 0.2
        
        # Close acceptance = cleaner
        if event.close_acceptance:
            quality += 0.1
        
        return max(0.0, min(1.0, quality))
    
    def _generate_description(self, event: StructureEvent, evidence_type: EvidenceType) -> str:
        """Generate human-readable evidence description"""
        direction = event.direction
        level = event.broken_level
        body_pct = int(event.body_strength * 100)
        
        if evidence_type == EvidenceType.BOS:
            desc = f"{direction} BOS confirmed"
        elif evidence_type == EvidenceType.CHOCH:
            desc = f"{direction} CHoCH detected"
        else:
            desc = f"{direction} swing break"
        
        # Add quality indicators
        if event.close_acceptance:
            desc += f" (body {body_pct}%, close accepted)"
        else:
            desc += f" (wick break, body {body_pct}%)"
        
        return desc
    
    def calculate_effective_score(self, evidence: StructureEvidence) -> float:
        """
        Calculate effective score for evidence.
        
        Formula: base_score * strength * quality
        
        This gives us a weighted contribution to final state.
        """
        base = self.BASE_SCORES.get(evidence.type, 0.0)
        effective = base * evidence.strength * evidence.quality
        
        return effective


class EvidenceAggregator:
    """
    Aggregates evidence into directional scores.
    
    Separates bullish vs bearish evidence for final state resolution.
    """
    
    def __init__(self):
        self.scorer = EvidenceScorer()
    
    def aggregate(self, evidence_list: List[StructureEvidence]) -> Dict:
        """
        Aggregate evidence into directional scores.
        
        Returns:
            {
                "bullish": float,
                "bearish": float,
                "evidence_items": List[str]
            }
        """
        bullish_score = 0.0
        bearish_score = 0.0
        evidence_descriptions = []
        
        for evidence in evidence_list:
            effective_score = self.scorer.calculate_effective_score(evidence)
            
            # Add to appropriate direction
            if evidence.direction == "bullish":
                bullish_score += effective_score
            elif evidence.direction == "bearish":
                bearish_score += effective_score
            
            # Collect description
            evidence_descriptions.append(evidence.description)
        
        return {
            "bullish": max(0.0, bullish_score),
            "bearish": max(0.0, bearish_score),
            "evidence_items": evidence_descriptions
        }
