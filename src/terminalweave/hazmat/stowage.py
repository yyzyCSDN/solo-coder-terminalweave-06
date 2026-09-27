from __future__ import annotations
from dataclasses import dataclass
from terminalweave.hazmat.compatibility import HazmatUnit, SegregationChecker
from terminalweave.hazmat.documents import DeclarationValidator, HazmatDeclaration
from terminalweave.hazmat.limits import HazmatCapacityLedger, HazmatPresence

@dataclass(frozen=True)
class StowageDecision:
    """Outcome of a joint hazmat stowage assessment.

    ``approved`` is True only when no check produced a reason; every
    rejection reason is preserved in ``reasons``.
    """
    approved: bool
    reasons: tuple[str, ...]

class StowageInspector:
    """Joint stowage check: documents, compatibility/distance, zone capacity.

    Every check fails closed — a missing declaration, a missing
    compatibility rule or a missing zone limit all reject the candidate —
    and the assessment is independent of the order containers are
    presented in.
    """

    def __init__(self, checker: SegregationChecker, ledger: HazmatCapacityLedger, declarations: DeclarationValidator | None=None):
        self.checker = checker
        self.ledger = ledger
        self.declarations = declarations or DeclarationValidator()

    def assess_candidate(self, candidate: HazmatUnit, net_kg: float, existing: list[HazmatUnit], declaration: HazmatDeclaration | None=None) -> StowageDecision:
        reasons: list[str] = []
        reasons.extend(self._document_reasons(candidate, declaration))
        for other in existing:
            if other.container_id == candidate.container_id:
                continue
            ok, reason = self.checker.check_pair(candidate, other)
            if not ok:
                reasons.append(f'{candidate.container_id}/{other.container_id}: {reason}')
        presence = HazmatPresence(candidate.container_id, candidate.block, candidate.class_code, net_kg)
        reasons.extend((f'{candidate.container_id}: {v}' for v in self.ledger.capacity_violations(presence)))
        return StowageDecision(approved=not reasons, reasons=tuple(reasons))

    def _document_reasons(self, candidate: HazmatUnit, declaration: HazmatDeclaration | None) -> list[str]:
        if declaration is None:
            return [f'{candidate.container_id}: declaration missing']
        reasons = [f'{candidate.container_id}: {error}' for error in self.declarations.validate(declaration)]
        if declaration.container_id != candidate.container_id:
            reasons.append(f'{candidate.container_id}: declaration belongs to {declaration.container_id}')
        if declaration.hazard_class.strip() and declaration.hazard_class != candidate.class_code:
            reasons.append(f'{candidate.container_id}: declared class {declaration.hazard_class} does not match stowed class {candidate.class_code}')
        return reasons
