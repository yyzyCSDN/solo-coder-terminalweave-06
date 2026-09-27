from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from terminalweave.core.errors import ValidationError, CapacityError

@dataclass(frozen=True)
class ZoneHazmatLimit:
    zone_id: str
    class_code: str
    max_units: int
    max_net_kg: float

    def __post_init__(self):
        if not self.zone_id.strip() or not self.class_code.strip():
            raise ValidationError('invalid hazmat limit')
        try:
            invalid_limits = self.max_units < 0 or self.max_net_kg < 0 or not isfinite(float(self.max_net_kg))
        except TypeError as exc:
            raise ValidationError('invalid hazmat limit') from exc
        if invalid_limits:
            raise ValidationError('hazmat limits cannot be negative')

@dataclass(frozen=True)
class HazmatPresence:
    container_id: str
    zone_id: str
    class_code: str
    net_kg: float

    def __post_init__(self):
        if not self.container_id.strip() or not self.zone_id.strip() or not self.class_code.strip():
            raise ValidationError('invalid hazmat presence')
        try:
            invalid_weight = not isfinite(self.net_kg) or self.net_kg < 0
        except TypeError:
            invalid_weight = True
        if invalid_weight:
            raise ValidationError('invalid hazmat presence')

class HazmatCapacityLedger:

    def __init__(self, limits: list[ZoneHazmatLimit]):
        self.limits = {(x.zone_id, x.class_code): x for x in limits}
        self.items: dict[str, HazmatPresence] = {}

    def _proposed_groups(
        self,
        items: list[HazmatPresence],
        *,
        include_existing: bool=True,
        excluded_existing_ids: set[str] | None=None,
    ) -> dict[tuple[str, str], list[HazmatPresence]]:
        excluded_existing_ids = excluded_existing_ids or set()
        entries: list[HazmatPresence] = list(items)
        if include_existing:
            entries.extend(
                existing
                for existing in self.items.values()
                if existing.container_id not in excluded_existing_ids
            )

        groups: dict[tuple[str, str], list[HazmatPresence]] = {}
        for entry in entries:
            groups.setdefault((entry.zone_id, entry.class_code), []).append(entry)
        return groups

    def check_items(
        self,
        items: list[HazmatPresence],
        *,
        include_existing: bool=True,
        excluded_existing_ids: set[str] | None=None,
    ) -> list[str]:
        groups = self._proposed_groups(
            items,
            include_existing=include_existing,
            excluded_existing_ids=excluded_existing_ids,
        )
        reasons = []
        for (zone_id, class_code), entries in sorted(groups.items()):
            limit = self.limits.get((zone_id, class_code))
            if not limit:
                reasons.append(f'zone {zone_id} class {class_code} has no capacity limit')
                continue
            unit_count = len(entries)
            total_net_kg = sum((x.net_kg for x in entries))
            if unit_count > limit.max_units:
                reasons.append(
                    f'zone {zone_id} class {class_code} unit capacity {limit.max_units} exceeded by {unit_count}'
                )
            if total_net_kg > limit.max_net_kg:
                reasons.append(
                    f'zone {zone_id} class {class_code} weight capacity {limit.max_net_kg:.1f}kg exceeded by {total_net_kg:.1f}kg'
                )
        return reasons

    def check_add(self, item: HazmatPresence) -> list[str]:
        if item.container_id in self.items:
            return ['container already present']
        return self.check_items([item])

    def can_add(self, item: HazmatPresence) -> bool:
        return not self.check_add(item)

    def add(self, item: HazmatPresence) -> None:
        reasons = self.check_add(item)
        if 'container already present' in reasons:
            raise ValidationError('container already present')
        if reasons:
            raise CapacityError('hazmat zone limit exceeded')
        self.items[item.container_id] = item

    def remove(self, container_id: str) -> None:
        self.items.pop(container_id, None)
