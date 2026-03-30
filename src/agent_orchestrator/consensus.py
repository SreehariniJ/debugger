"""
consensus — Multi-agent voting and decision validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Vote:
    agent: str
    decision: str  # "approve", "reject", "abstain"
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    has_veto: bool = False


@dataclass
class ConsensusResult:
    decision: str  # "approved", "rejected", "inconclusive"
    for_count: int = 0
    against_count: int = 0
    abstain_count: int = 0
    vetoed_by: str | None = None
    votes: list[Vote] = field(default_factory=list)
    avg_confidence: float = 0.0


class ConsensusEngine:
    """
    Multi-agent consensus mechanism.

    Rules:
    - For critical decisions, 2/3 majority required.
    - CriticAgent and SecurityAgent have veto power on patches.
    - Confidence-weighted voting for tie-breaking.
    """

    VETO_AGENTS = {"CriticAgent", "SecurityAgent"}
    MAJORITY_THRESHOLD = 2 / 3

    def vote(self, votes: list[Vote]) -> ConsensusResult:
        result = ConsensusResult(decision="inconclusive", votes=votes)

        if not votes:
            return result

        # Check for vetoes
        for v in votes:
            if v.has_veto and v.decision == "reject":
                result.decision = "rejected"
                result.vetoed_by = v.agent
                return result

        # Count votes
        for v in votes:
            if v.decision == "approve":
                result.for_count += 1
            elif v.decision == "reject":
                result.against_count += 1
            else:
                result.abstain_count += 1

        total_decisive = result.for_count + result.against_count
        if total_decisive == 0:
            result.decision = "inconclusive"
            return result

        approval_ratio = result.for_count / total_decisive
        result.avg_confidence = sum(v.confidence for v in votes) / len(votes)

        if approval_ratio >= self.MAJORITY_THRESHOLD:
            result.decision = "approved"
        elif approval_ratio <= (1 - self.MAJORITY_THRESHOLD):
            result.decision = "rejected"
        else:
            # Tie-break by confidence-weighted voting
            weighted_approve = sum(v.confidence for v in votes if v.decision == "approve")
            weighted_reject = sum(v.confidence for v in votes if v.decision == "reject")
            result.decision = "approved" if weighted_approve >= weighted_reject else "rejected"

        return result
