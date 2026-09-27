from terminalweave.hazmat.compatibility import (
    CompatibilityMatrix,
    HazmatUnit,
    SegregationChecker,
)
from terminalweave.hazmat.documents import HazmatDeclaration
from terminalweave.hazmat.limits import (
    HazmatCapacityLedger,
    HazmatPresence,
    ZoneHazmatLimit,
)
from terminalweave.hazmat.stowage import StowageInspector


def test_hazmat_pair_result_is_independent_of_input_order():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    checker = SegregationChecker(matrix)
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0)
    corrosive = HazmatUnit("B", "8", "Z1", 12.0, 0.0)
    assert checker.check_pair(flammable, corrosive) == (True, "compatible")
    assert checker.check_pair(corrosive, flammable) == (True, "compatible")


def test_missing_rule_rejects_identically_in_both_orders():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    checker = SegregationChecker(matrix)
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0)
    oxidizer = HazmatUnit("B", "5.1", "Z1", 30.0, 0.0)
    forward = checker.check_pair(flammable, oxidizer)
    reverse = checker.check_pair(oxidizer, flammable)
    assert forward == reverse
    assert forward[0] is False
    assert "no compatibility rule" in forward[1]


def test_validate_layout_keeps_every_violation_reason():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    matrix.set_incompatible("3", "5.1")
    checker = SegregationChecker(matrix)
    units = [
        HazmatUnit("A", "3", "Z1", 0.0, 0.0),
        HazmatUnit("B", "8", "Z1", 4.0, 0.0),   # too close to A
        HazmatUnit("C", "5.1", "Z1", 50.0, 0.0),  # prohibited near A
        HazmatUnit("D", "2.1", "Z1", 90.0, 0.0),  # no rule against A/B/C
    ]
    violations = checker.validate_layout(units)
    assert len(violations) == 6
    assert any("A/B" in v and "requires 10.0m separation" in v for v in violations)
    assert any("A/C" in v and "prohibited" in v for v in violations)
    assert sum("no compatibility rule" in v for v in violations) == 4


def _inspector(max_units=2, max_net_kg=1000.0):
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    ledger = HazmatCapacityLedger([ZoneHazmatLimit("Z1", "3", max_units, max_net_kg)])
    return StowageInspector(SegregationChecker(matrix), ledger)


def _declaration(container_id="CAND"):
    return HazmatDeclaration(container_id, "UN1203", "GASOLINE", "3", "II", "+1 555 123 4567", True)


def test_joint_assessment_rejects_missing_declaration():
    inspector = _inspector()
    candidate = HazmatUnit("CAND", "3", "Z1", 0.0, 0.0)
    decision = inspector.assess_candidate(candidate, 100.0, [])
    assert not decision.approved
    assert decision.reasons == ("CAND: declaration missing",)


def test_joint_assessment_rejects_incomplete_declaration():
    inspector = _inspector()
    candidate = HazmatUnit("CAND", "3", "Z1", 0.0, 0.0)
    incomplete = HazmatDeclaration("CAND", "", "", "", None, "", False)
    decision = inspector.assess_candidate(candidate, 100.0, [], incomplete)
    assert not decision.approved
    assert any("UN number invalid" in r for r in decision.reasons)
    assert any("declaration unsigned" in r for r in decision.reasons)


def test_joint_assessment_collects_reasons_from_all_checks():
    inspector = _inspector(max_units=1)
    ledger = inspector.ledger
    ledger.add(HazmatPresence("A", "Z1", "3", 900.0))
    existing = [HazmatUnit("A", "3", "Z1", 0.0, 0.0), HazmatUnit("B", "8", "Z1", 5.0, 0.0)]
    candidate = HazmatUnit("CAND", "3", "Z1", 1.0, 0.0)
    decision = inspector.assess_candidate(candidate, 200.0, existing, _declaration())
    assert not decision.approved
    # distance violation against B, both capacity violations, all kept together
    assert any("CAND/B" in r and "separation" in r for r in decision.reasons)
    assert any("unit limit" in r for r in decision.reasons)
    assert any("net weight limit" in r for r in decision.reasons)


def test_joint_assessment_is_independent_of_existing_order():
    inspector = _inspector()
    existing = [HazmatUnit("A", "3", "Z1", 0.0, 0.0), HazmatUnit("B", "8", "Z1", 5.0, 0.0)]
    candidate = HazmatUnit("CAND", "3", "Z1", 1.0, 0.0)
    forward = inspector.assess_candidate(candidate, 100.0, existing, _declaration())
    reverse = inspector.assess_candidate(candidate, 100.0, list(reversed(existing)), _declaration())
    assert forward.approved == reverse.approved
    assert sorted(forward.reasons) == sorted(reverse.reasons)


def test_joint_assessment_approves_when_everything_is_clean():
    inspector = _inspector()
    existing = [HazmatUnit("B", "8", "Z1", 20.0, 0.0)]
    candidate = HazmatUnit("CAND", "3", "Z1", 0.0, 0.0)
    decision = inspector.assess_candidate(candidate, 100.0, existing, _declaration())
    assert decision.approved
    assert decision.reasons == ()
