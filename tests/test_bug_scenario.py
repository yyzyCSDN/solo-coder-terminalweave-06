from terminalweave.hazmat.compatibility import (
    CompatibilityMatrix,
    HazmatUnit,
    SegregationChecker,
)


def test_hazmat_pair_result_is_independent_of_input_order():
    matrix = CompatibilityMatrix()
    matrix.set_compatible("3", "8", 10.0)
    checker = SegregationChecker(matrix)
    flammable = HazmatUnit("A", "3", "Z1", 0.0, 0.0)
    corrosive = HazmatUnit("B", "8", "Z1", 12.0, 0.0)
    assert checker.check_pair(flammable, corrosive) == (True, "compatible")
    assert checker.check_pair(corrosive, flammable) == (True, "compatible")
