from __future__ import annotations

import math
from typing import Sequence

from .compiler import PolicyCompiler
from .features import ConfidenceLiftedEncoder, critical_field_grounding
from .schemas import (
    ActionCertificate,
    RuntimeEvidence,
    SelectionResult,
    ToolAction,
)


PROXIMITY_FEATURES = (
    "trusted_intent_support",
    "prerequisite_support",
    "completion_sufficiency",
    "entity_grounding_confidence",
    "effect_class",
    "data_sensitivity",
    "sink_externality",
    "privacy_egress",
    "critical_argument_grounding",
    "state_read_necessity",
    "write_authorization_strength",
    "scope_precision",
    "financial_risk",
    "state_cleanliness_cost",
)


class ConfidenceLiftedActionSelector:
    """Select actions inside a confidence-lifted feasible region."""

    def __init__(
        self,
        *,
        encoder: ConfidenceLiftedEncoder | None = None,
        compiler: PolicyCompiler | None = None,
        utility_weight: float = 1.0,
        interior_weight: float = 0.25,
        proximity_weight: float = 0.15,
        confidence_weight: float = 0.15,
        delta: float = 1e-3,
    ) -> None:
        self.encoder = encoder or ConfidenceLiftedEncoder()
        self.compiler = compiler or PolicyCompiler()
        self.utility_weight = float(utility_weight)
        self.interior_weight = float(interior_weight)
        self.proximity_weight = float(proximity_weight)
        self.confidence_weight = float(confidence_weight)
        self.delta = float(delta)

    def select(
        self,
        actions: Sequence[ToolAction],
        evidence: RuntimeEvidence,
        *,
        policies: Sequence[str] | None = None,
    ) -> SelectionResult:
        action_tuple = tuple(actions)
        if not action_tuple:
            return SelectionResult(
                decision="NO_CANDIDATE",
                selected=None,
                selected_certificate=None,
                certificates=(),
                region_metadata={"reason": "empty_candidate_set"},
            )

        active_policies = tuple(policies or evidence.policies)
        region = self.compiler.compile(active_policies, evidence)
        vectors = tuple(self.encoder.encode(action, evidence) for action in action_tuple)
        anchor = vectors[0]

        certificates: list[ActionCertificate] = []
        for action, vector in zip(action_tuple, vectors):
            margins = region.margins(vector)
            feasible = all(margin.slack >= 0.0 for margin in margins if not margin.soft)
            utility = self._utility(action, vector.as_dict())
            interior = self._interior_score(margins)
            proximity = vector.squared_distance(anchor, PROXIMITY_FEATURES)
            final_score = (
                self.utility_weight * utility
                + self.interior_weight * interior
                + self.confidence_weight * vector.get("confidence")
                - self.proximity_weight * proximity
            )
            certificates.append(
                ActionCertificate(
                    action_id=action.id,
                    tool_name=action.tool_name,
                    features=vector.as_dict(),
                    margins=margins,
                    feasible=feasible,
                    utility=utility,
                    interior_score=interior,
                    proximity_penalty=proximity,
                    final_score=final_score,
                )
            )

        feasible_indices = [idx for idx, cert in enumerate(certificates) if cert.feasible]
        metadata = dict(region.metadata)
        metadata.update(
            {
                "feature_count": len(self.encoder.feature_names),
                "candidate_count": len(action_tuple),
                "feasible_candidate_count": len(feasible_indices),
                "policy_count": len(active_policies),
            }
        )
        if not feasible_indices:
            return SelectionResult(
                decision="BLOCK_OR_CLARIFY",
                selected=None,
                selected_certificate=None,
                certificates=tuple(certificates),
                region_metadata=metadata,
            )

        best_idx = max(feasible_indices, key=lambda idx: certificates[idx].final_score)
        return SelectionResult(
            decision="ALLOW",
            selected=action_tuple[best_idx],
            selected_certificate=certificates[best_idx],
            certificates=tuple(certificates),
            region_metadata=metadata,
        )

    def repair(
        self,
        action: ToolAction,
        evidence: RuntimeEvidence,
        *,
        policies: Sequence[str] | None = None,
    ) -> SelectionResult | None:
        """Project a blocked action by dropping unsupported optional fields."""
        required = set(evidence.required_args(action.tool_name))
        field_scores = critical_field_grounding(action, evidence)
        removable = {
            key
            for key, score in field_scores.items()
            if score <= 0.0 and key not in required
        }
        if not removable:
            return None
        repaired_arguments = {
            key: value for key, value in action.arguments.items() if key not in removable
        }
        # Required fields can contain the actual effect (email body, transfer
        # amount, record title). Requiring an optional field to survive wrongly
        # discards complete repaired calls. Only reject genuine locator-only
        # remainders; the selector still validates grounding and schema below.
        locator_keys = {
            "id", "record_id", "file_id", "task_id", "event_id", "user_id",
            "recipient", "recipients", "to", "email", "user_email", "channel",
            "account", "iban", "url", "destination",
        }
        if not repaired_arguments or all(str(key).lower() in locator_keys for key in repaired_arguments):
            return None
        repaired = ToolAction(
            id=f"{action.id}:repair",
            tool_name=action.tool_name,
            arguments=repaired_arguments,
            rationale=action.rationale,
            utility_hint=action.utility_hint,
        )
        result = self.select((repaired,), evidence, policies=policies)
        return result if result.selected is not None else None

    @staticmethod
    def _utility(action: ToolAction, features: dict[str, float]) -> float:
        if action.utility_hint:
            return float(action.utility_hint)
        return (
            0.30 * features["trusted_intent_support"]
            + 0.20 * features["prerequisite_support"]
            + 0.18 * features["completion_sufficiency"]
            + 0.12 * features["entity_grounding_confidence"]
            + 0.10 * features["schema_format_validity"]
            + 0.08 * features["state_read_necessity"]
            + 0.07 * features["critical_argument_grounding"]
            + 0.06 * features["write_authorization_strength"]
            + 0.04 * features["scope_precision"]
            + 0.06 * features["source_grounding"]
            + 0.04 * features["confidence"]
            - 0.20 * features["overreach_risk"]
            - 0.16 * features["untrusted_instruction_alignment"]
            - 0.14 * features["state_cleanliness_cost"]
            - 0.12 * features["privacy_egress"]
            - 0.06 * features["sink_externality"]
        )

    def _interior_score(self, margins: Sequence[object]) -> float:
        score = 0.0
        for margin in margins:
            slack = max(0.0, float(margin.slack))
            score += float(margin.severity) * math.log(self.delta + slack)
        return score
