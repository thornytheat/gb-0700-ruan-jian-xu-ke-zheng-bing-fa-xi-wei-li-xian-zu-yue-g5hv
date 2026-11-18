from decimal import Decimal

from app import coverage
from app.pipeline import run


def ctx(*rows):
    return {"normalized": [dict(a=Decimal(x[0]), b=Decimal(x[1]), rev=x[2], kind=x[3], canonical="CAD")
                           for x in rows]}


def test_no_evidence_all_confirmed():
    assert coverage.proof({"normalized": []}, "CAD", 0, 10) == coverage.CONFIRMED


def test_gap_marks_pending():
    state = ctx((0, 10, 1, "gap"))
    assert coverage.proof(state, "CAD", 2, 8) == coverage.PENDING
    assert coverage.proof(state, "CAD", 10, 20) == coverage.CONFIRMED


def test_gap_half_open_boundary():
    state = ctx((0, 10, 1, "gap"))
    assert coverage.proof(state, "CAD", 10, 20) == coverage.CONFIRMED
    assert coverage.proof(state, "CAD", 5, 10) == coverage.PENDING


def test_coverage_higher_version_clears_gap():
    state = ctx((0, 10, 1, "gap"), (0, 10, 2, "coverage"))
    assert coverage.gaps_at(state, "CAD") == []


def test_coverage_same_version_does_not_clear_gap():
    state = ctx((0, 10, 1, "gap"), (0, 10, 1, "coverage"))
    assert len(coverage.gaps_at(state, "CAD")) == 1


def test_coverage_partial_does_not_clear_gap():
    state = ctx((0, 10, 1, "gap"), (0, 5, 2, "coverage"))
    assert len(coverage.gaps_at(state, "CAD")) == 1


def test_other_product_gap_ignored():
    state = {"normalized": [{"a": Decimal(0), "b": Decimal(10), "rev": 1,
                             "kind": "gap", "canonical": "RENDER"}]}
    assert coverage.proof(state, "CAD", 0, 10) == coverage.CONFIRMED
