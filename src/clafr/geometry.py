from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Protocol

from .schemas import ConstraintMargin, FeatureVector


class Constraint(Protocol):
    id: str
    source: str
    soft: bool
    severity: float

    def margin(self, vector: FeatureVector) -> ConstraintMargin:
        ...


def _dot(weights: Mapping[str, float], vector: FeatureVector) -> float:
    return sum(float(weight) * vector.get(name) for name, weight in weights.items())


def _norm(weights: Mapping[str, float]) -> float:
    value = math.sqrt(sum(float(weight) ** 2 for weight in weights.values()))
    return value if value > 1e-12 else 1.0


def _stable_slack(bound: float, value: float) -> float:
    """Snap only machine-roundoff at a boundary, consistently for both shapes."""
    slack = float(bound) - float(value)
    scale = max(1.0, abs(float(bound)), abs(float(value)))
    return 0.0 if abs(slack) <= 16 * math.ulp(scale) else slack


@dataclass(frozen=True, slots=True)
class LinearFacet:
    """A linear facet expressed as w^T z <= bound."""

    id: str
    weights: Mapping[str, float]
    bound: float
    description: str
    repair_hint: str
    source: str = "linear_facet"
    soft: bool = False
    severity: float = 1.0

    def margin(self, vector: FeatureVector) -> ConstraintMargin:
        value = _dot(self.weights, vector)
        slack = _stable_slack(self.bound, value)
        return ConstraintMargin(
            constraint_id=self.id,
            source=self.source,
            value=value,
            bound=float(self.bound),
            slack=slack,
            normalized_slack=slack / _norm(self.weights),
            description=self.description,
            repair_hint=self.repair_hint,
            soft=self.soft,
            severity=float(self.severity),
        )


@dataclass(frozen=True, slots=True)
class RiskBudgetCone:
    """Convex joint-risk budget: ||W_r r||_2 <= bound + w_c^T c."""

    id: str
    risk_weights: Mapping[str, float]
    credit_weights: Mapping[str, float]
    bound: float
    description: str
    repair_hint: str
    source: str = "joint_risk_budget"
    soft: bool = False
    severity: float = 1.0

    def risk_norm(self, vector: FeatureVector) -> float:
        return math.sqrt(
            sum((float(weight) * max(0.0, vector.get(name))) ** 2 for name, weight in self.risk_weights.items())
        )

    def credit(self, vector: FeatureVector) -> float:
        return sum(float(weight) * max(0.0, vector.get(name)) for name, weight in self.credit_weights.items())

    def value(self, vector: FeatureVector) -> float:
        return self.risk_norm(vector) - self.credit(vector)

    def margin(self, vector: FeatureVector) -> ConstraintMargin:
        weights = {**self.risk_weights, **self.credit_weights}
        value = self.value(vector)
        slack = _stable_slack(self.bound, value)
        return ConstraintMargin(
            constraint_id=self.id,
            source=self.source,
            value=value,
            bound=float(self.bound),
            slack=slack,
            normalized_slack=slack / _norm(weights),
            description=self.description,
            repair_hint=self.repair_hint,
            soft=self.soft,
            severity=float(self.severity),
        )


@dataclass(frozen=True, slots=True)
class FeasibleRegion:
    constraints: tuple[Constraint, ...]

    def margins(self, vector: FeatureVector) -> tuple[ConstraintMargin, ...]:
        return tuple(constraint.margin(vector) for constraint in self.constraints)

    def feasible(self, vector: FeatureVector) -> bool:
        return all(margin.slack >= 0.0 for margin in self.margins(vector) if not margin.soft)

    @property
    def metadata(self) -> dict[str, int]:
        risk_budgets = sum(1 for item in self.constraints if isinstance(item, RiskBudgetCone))
        linear_facets = sum(1 for item in self.constraints if isinstance(item, LinearFacet))
        hard_constraints = sum(1 for item in self.constraints if not item.soft)
        soft_constraints = len(self.constraints) - hard_constraints
        return {
            "constraint_count": len(self.constraints),
            "linear_facet_count": linear_facets,
            "joint_risk_budget_count": risk_budgets,
            "hard_constraint_count": hard_constraints,
            "soft_constraint_count": soft_constraints,
        }
