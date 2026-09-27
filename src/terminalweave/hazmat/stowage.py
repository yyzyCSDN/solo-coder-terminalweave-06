from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple

from terminalweave.core.errors import ValidationError
from terminalweave.hazmat.compatibility import CompatibilityMatrix, HazmatUnit, SegregationChecker
from terminalweave.hazmat.documents import DeclarationValidator, HazmatDeclaration
from terminalweave.hazmat.limits import HazmatCapacityLedger, HazmatPresence, ZoneHazmatLimit


class StowageAssessment(NamedTuple):
    allowed: bool
    reasons: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.allowed


StowageResult = StowageAssessment
StowageCheckResult = StowageAssessment
JointStowageResult = StowageAssessment


class HazmatStowageChecker:
    """Joint compatibility, segregation, documentation, and zone-capacity check."""

    def __init__(
        self,
        matrix: CompatibilityMatrix,
        capacity_ledger: HazmatCapacityLedger | Iterable[ZoneHazmatLimit],
        declaration_validator: DeclarationValidator | None=None,
    ):
        if isinstance(capacity_ledger, HazmatCapacityLedger):
            ledger = capacity_ledger
        elif isinstance(capacity_ledger, list):
            ledger = HazmatCapacityLedger(capacity_ledger)
        else:
            ledger = HazmatCapacityLedger(list(capacity_ledger))
        self.matrix = matrix
        self.capacity_ledger = ledger
        self.segregation = SegregationChecker(matrix)
        self.declaration_validator = declaration_validator or DeclarationValidator()

    @classmethod
    def from_limits(
        cls,
        matrix: CompatibilityMatrix,
        limits: Iterable[ZoneHazmatLimit],
        declaration_validator: DeclarationValidator | None=None,
    ) -> 'HazmatStowageChecker':
        return cls(matrix, HazmatCapacityLedger(list(limits)), declaration_validator)

    def assess(
        self,
        units: list[HazmatUnit],
        declarations: Mapping[str, HazmatDeclaration] | list[HazmatDeclaration] | None=None,
        *,
        include_existing: bool=True,
        documents: Mapping[str, HazmatDeclaration] | list[HazmatDeclaration] | None=None,
    ) -> StowageAssessment:
        if documents is not None and declarations is not None:
            raise ValidationError('provide declarations or documents, not both')
        if documents is not None:
            declarations = documents
        reasons: list[str] = []
        normalized_units, unit_errors = self._normalize_units(units)
        declarations_by_id, declaration_errors = self._normalize_declarations(declarations)
        reasons.extend(unit_errors)
        reasons.extend(declaration_errors)

        for unit in sorted(normalized_units, key=self._unit_key):
            declaration = declarations_by_id.get(unit.container_id)
            if declaration is None:
                reasons.append(f'{unit.container_id}: hazmat declaration missing')
                continue
            for error in self.declaration_validator.validate(declaration):
                reasons.append(f'{unit.container_id}: {error}')
            if (declaration.hazard_class or '').strip() != unit.class_code:
                reasons.append(
                    f'{unit.container_id}: declared class {declaration.hazard_class} does not match unit class {unit.class_code}'
                )

        ordered_units = sorted(normalized_units, key=self._unit_key)
        for i, a in enumerate(ordered_units):
            for b in ordered_units[i + 1:]:
                pair = '/'.join(sorted((a.container_id, b.container_id)))
                for reason in self.segregation.pair_reasons(a, b):
                    reasons.append(f'{pair}: {reason}')

        proposed_presences = [
            HazmatPresence(
                container_id=unit.container_id,
                zone_id=unit.block,
                class_code=unit.class_code,
                net_kg=unit.net_kg,
            )
            for unit in normalized_units
        ]
        proposed_ids = {presence.container_id for presence in proposed_presences}
        for reason in self.capacity_ledger.check_items(
            proposed_presences,
            include_existing=include_existing,
            excluded_existing_ids=proposed_ids,
        ):
            reasons.append(reason)

        ordered_reasons = tuple(sorted(reasons))
        return StowageAssessment(not ordered_reasons, ordered_reasons)

    def assess_pair(
        self,
        a: HazmatUnit,
        b: HazmatUnit,
        declaration_a: HazmatDeclaration | None=None,
        declaration_b: HazmatDeclaration | None=None,
        **kwargs,
    ) -> StowageAssessment:
        declarations = [d for d in (declaration_a, declaration_b) if d is not None]
        return self.assess([a, b], declarations, **kwargs)

    def check(
        self,
        units: list[HazmatUnit],
        declarations: Mapping[str, HazmatDeclaration] | list[HazmatDeclaration] | None=None,
        **kwargs,
    ) -> StowageAssessment:
        return self.assess(units, declarations, **kwargs)

    def check_stowage(self, units: list[HazmatUnit], declarations=None, **kwargs) -> StowageAssessment:
        return self.assess(units, declarations, **kwargs)

    def validate_stowage(self, units: list[HazmatUnit], declarations=None, **kwargs) -> StowageAssessment:
        return self.assess(units, declarations, **kwargs)

    @staticmethod
    def _unit_key(unit: HazmatUnit) -> tuple[str, str, str, float, float, float]:
        return (
            unit.container_id,
            unit.class_code,
            unit.block,
            unit.x_m,
            unit.y_m,
            unit.net_kg,
        )

    def _normalize_units(self, units) -> tuple[list[HazmatUnit], list[str]]:
        normalized: list[HazmatUnit] = []
        errors: list[str] = []
        seen: dict[str, HazmatUnit] = {}
        try:
            raw_units = list(units or [])
        except TypeError:
            return [], ['hazmat units must be a collection']

        for raw in raw_units:
            try:
                unit = self._coerce_unit(raw)
            except ValidationError as exc:
                identifier = self._raw_identifier(raw)
                errors.append(f'{identifier}: {exc}')
                continue
            if unit.container_id in seen:
                errors.append(f'{unit.container_id}: duplicate hazmat unit')
                continue
            seen[unit.container_id] = unit
            normalized.append(unit)
        return normalized, errors

    @staticmethod
    def _coerce_unit(raw) -> HazmatUnit:
        if isinstance(raw, HazmatUnit):
            return raw
        if not isinstance(raw, Mapping):
            raise ValidationError('invalid hazmat unit')
        try:
            return HazmatUnit(
                container_id=raw['container_id'],
                class_code=raw['class_code'],
                block=raw['block'],
                x_m=raw['x_m'],
                y_m=raw['y_m'],
                net_kg=raw.get('net_kg', 0.0),
            )
        except KeyError as exc:
            raise ValidationError(f'{exc.args[0]} missing') from exc
        except (TypeError, ValueError) as exc:
            raise ValidationError('invalid hazmat unit') from exc

    def _normalize_declarations(self, raw_declarations) -> tuple[dict[str, HazmatDeclaration], list[str]]:
        declarations: dict[str, HazmatDeclaration] = {}
        errors: list[str] = []
        if raw_declarations is None:
            return declarations, errors
        if isinstance(raw_declarations, Mapping):
            iterable = raw_declarations.items()
        else:
            try:
                iterable = ((None, value) for value in raw_declarations)
            except TypeError:
                return {}, ['hazmat declarations must be a collection']

        for key, raw in iterable:
            try:
                declaration = self._coerce_declaration(raw, key)
            except ValidationError as exc:
                identifier = key if isinstance(key, str) else self._raw_identifier(raw)
                errors.append(f'{identifier}: {exc}')
                continue
            existing = declarations.get(declaration.container_id)
            if existing is not None and existing != declaration:
                errors.append(f'{declaration.container_id}: conflicting hazmat declarations')
                continue
            declarations[declaration.container_id] = declaration
        return declarations, errors

    @staticmethod
    def _coerce_declaration(raw, key) -> HazmatDeclaration:
        if isinstance(raw, HazmatDeclaration):
            return raw
        if not isinstance(raw, Mapping):
            raise ValidationError('invalid hazmat declaration')
        try:
            return HazmatDeclaration(
                container_id=raw.get('container_id', key),
                un_number=raw['un_number'],
                proper_name=raw['proper_name'],
                hazard_class=raw['hazard_class'],
                packing_group=raw.get('packing_group'),
                emergency_contact=raw.get('emergency_contact'),
                signed=raw.get('signed', False),
            )
        except KeyError as exc:
            raise ValidationError(f'{exc.args[0]} missing') from exc
        except (TypeError, ValueError) as exc:
            raise ValidationError('invalid hazmat declaration') from exc

    @staticmethod
    def _raw_identifier(raw) -> str:
        if isinstance(raw, Mapping):
            value = raw.get('container_id')
            return value if isinstance(value, str) and value.strip() else 'unknown container'
        return getattr(raw, 'container_id', 'unknown container')


class JointSegregationChecker(HazmatStowageChecker):
    pass


StowageChecker = HazmatStowageChecker
JointStowageChecker = HazmatStowageChecker
