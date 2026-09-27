from __future__ import annotations
from dataclasses import dataclass
from terminalweave.core.errors import ValidationError, CapacityError

@dataclass(frozen=True)
class ZoneHazmatLimit:
    zone_id: str
    class_code: str
    max_units: int
    max_net_kg: float

    def __post_init__(self):
        if self.max_units < 0 or self.max_net_kg < 0:
            raise ValidationError('hazmat limits cannot be negative')

@dataclass(frozen=True)
class HazmatPresence:
    container_id: str
    zone_id: str
    class_code: str
    net_kg: float

class HazmatCapacityLedger:

    def __init__(self, limits: list[ZoneHazmatLimit]):
        self.limits = {(x.zone_id, x.class_code): x for x in limits}
        self.items: dict[str, HazmatPresence] = {}

    def capacity_violations(self, item: HazmatPresence) -> list[str]:
        limit = self.limits.get((item.zone_id, item.class_code))
        if limit is None:
            return [f'no hazmat limit for zone {item.zone_id} class {item.class_code}']
        existing = [x for x in self.items.values() if x.zone_id == item.zone_id and x.class_code == item.class_code]
        violations = []
        if len(existing) + 1 > limit.max_units:
            violations.append(f'zone {item.zone_id} class {item.class_code} unit limit {limit.max_units} would be exceeded')
        if sum((x.net_kg for x in existing)) + item.net_kg > limit.max_net_kg:
            violations.append(f'zone {item.zone_id} class {item.class_code} net weight limit {limit.max_net_kg}kg would be exceeded')
        return violations

    def can_add(self, item: HazmatPresence) -> bool:
        return not self.capacity_violations(item)

    def add(self, item: HazmatPresence) -> None:
        if item.container_id in self.items:
            raise ValidationError('container already present')
        if not self.can_add(item):
            raise CapacityError('hazmat zone limit exceeded')
        self.items[item.container_id] = item

    def remove(self, container_id: str) -> None:
        self.items.pop(container_id, None)
