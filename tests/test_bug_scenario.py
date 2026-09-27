from terminalweave.hazmat import (
    CompatibilityMatrix,
    DeclarationValidator,
    HazmatDeclaration,
    HazmatStowageChecker,
    HazmatUnit,
    SegregationChecker,
    ZoneHazmatLimit,
)
from terminalweave.hazmat.limits import HazmatCapacityLedger


def test_hazmat_pair_result_is_independent_of_input_order():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    checker = SegregationChecker(matrix)
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0)
    corrosive = HazmatUnit("B", "8", "Z1", 12.0, 0.0)
    assert checker.check_pair(flammable, corrosive) == (True, "compatible")
    assert checker.check_pair(corrosive, flammable) == (True, "compatible")


def test_joint_assessment_is_order_independent_and_reports_all_failures():
    matrix = CompatibilityMatrix()
    matrix.set_incompatible("3", "8")
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0, 10.0)
    corrosive = HazmatUnit("B", "8", "Z1", 12.0, 0.0, 10.0)
    declarations = [
        HazmatDeclaration("A", "UN1203", "Gasoline", "3", "II", "5551234567", True),
        HazmatDeclaration("B", "UN1789", "Acid", "8", "II", "5551234567", True),
    ]
    ledger = HazmatCapacityLedger([
        ZoneHazmatLimit("Z1", "3", 1, 100.0),
        ZoneHazmatLimit("Z1", "8", 1, 5.0),
    ])
    checker = HazmatStowageChecker(matrix, ledger)

    first = checker.assess([flammable, corrosive], declarations, include_existing=False)
    second = checker.assess([corrosive, flammable], reversed(declarations), include_existing=False)

    assert not first.allowed
    assert first == second
    assert any("prohibited" in reason for reason in first.reasons)
    assert any("weight capacity" in reason for reason in first.reasons)


def test_incomplete_documentation_fails_closed_without_reusing_previous_result():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0)
    corrosive = HazmatUnit("B", "8", "Z1", 12.0, 0.0)
    valid = HazmatDeclaration("B", "UN1789", "Acid", "8", "II", "5551234567", True)
    ledger = HazmatCapacityLedger([
        ZoneHazmatLimit("Z1", "3", 2, 100.0),
        ZoneHazmatLimit("Z1", "8", 2, 100.0),
    ])
    checker = HazmatStowageChecker(matrix, ledger)

    missing_document = checker.assess([flammable, corrosive], {"B": valid}, include_existing=False)
    assert not missing_document.allowed
    assert missing_document.reasons == ("A: hazmat declaration missing",)

    incomplete_field = HazmatDeclaration("A", "UN1203", "Gasoline", "3", "II", None, True)
    field_errors = DeclarationValidator().validate(incomplete_field)
    assert field_errors == ["emergency contact invalid"]
