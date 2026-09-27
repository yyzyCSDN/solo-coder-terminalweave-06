from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from terminalweave.core.errors import ValidationError, SafetyConstraintError

_MISSING = object()

@dataclass(frozen=True)
class HazmatClass:
    code: str
    name: str
    default_separation_m: float

    def __post_init__(self) -> None:
        if not self.code.strip() or self.default_separation_m < 0:
            raise ValidationError('invalid hazardous class')

@dataclass(frozen=True)
class HazmatUnit:
    container_id: str
    class_code: str
    block: str
    x_m: float
    y_m: float
    net_kg: float = 0.0

    def __post_init__(self) -> None:
        if not self.container_id.strip() or not self.class_code.strip() or not self.block.strip():
            raise ValidationError('invalid hazmat unit')
        try:
            if not isfinite(self.x_m) or not isfinite(self.y_m) or not isfinite(self.net_kg) or self.net_kg < 0:
                raise ValidationError('invalid hazmat unit')
        except TypeError as exc:
            raise ValidationError('invalid hazmat unit') from exc

class CompatibilityMatrix:

    def __init__(self):
        self._rules: dict[tuple[str, str], float | None] = {}

    @staticmethod
    def _key(a: str, b: str) -> tuple[str, str]:
        return tuple(sorted((a, b)))

    def _set(self, a: str, b: str, value: float | None) -> None:
        key = self._key(a, b)
        if key in self._rules and self._rules[key] != value:
            raise ValidationError(f'conflicting compatibility rule for {key[0]}/{key[1]}')
        self._rules[key] = value

    def set_compatible(self, a: str, b: str, minimum_separation_m: float=0.0) -> None:
        if minimum_separation_m < 0 or not isfinite(minimum_separation_m):
            raise ValidationError('separation cannot be negative')
        self._set(a, b, float(minimum_separation_m))

    def set_incompatible(self, a: str, b: str) -> None:
        self._set(a, b, None)

    def inspect(self, a: str, b: str) -> float | None | object:
        if a == b:
            return 0.0
        return self._rules.get(self._key(a, b), _MISSING)

    def has_rule(self, a: str, b: str) -> bool:
        return self.inspect(a, b) is not _MISSING

    def requirement(self, a: str, b: str) -> float | None:
        requirement = self.inspect(a, b)
        if requirement is _MISSING:
            raise SafetyConstraintError(f'no compatibility rule for {a}/{b}')
        return requirement

class SegregationChecker:

    def __init__(self, matrix: CompatibilityMatrix):
        self.matrix = matrix

    @staticmethod
    def distance(a: HazmatUnit, b: HazmatUnit) -> float:
        return ((a.x_m - b.x_m) ** 2 + (a.y_m - b.y_m) ** 2) ** 0.5

    def pair_reasons(self, a: HazmatUnit, b: HazmatUnit) -> list[str]:
        requirement = self.matrix.inspect(a.class_code, b.class_code)
        if requirement is _MISSING:
            return ['compatibility rule missing']
        if requirement is None:
            return ['classes are prohibited from co-location']
        actual = self.distance(a, b)
        if actual + 1e-09 < requirement:
            return [f'requires {requirement:.1f}m separation, observed {actual:.1f}m']
        return []

    def check_pair(self, a: HazmatUnit, b: HazmatUnit) -> tuple[bool, str]:
        reasons = self.pair_reasons(a, b)
        if reasons:
            return (False, reasons[0])
        return (True, 'compatible')

    def validate_layout(self, units: list[HazmatUnit]) -> list[str]:
        violations = []
        ordered = sorted(units, key=lambda u: (u.container_id, u.class_code, u.block, u.x_m, u.y_m, u.net_kg))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                pair = '/'.join(sorted((a.container_id, b.container_id)))
                for reason in self.pair_reasons(a, b):
                    violations.append(f'{pair}: {reason}')
        return violations

    def candidate_is_safe(self, candidate: HazmatUnit, existing: list[HazmatUnit]) -> bool:
        return all((self.check_pair(candidate, other)[0] for other in existing))
