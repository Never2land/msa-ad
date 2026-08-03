"""Correctness tests for seeded-fault coverage verification.

Counts and proportions here are small enough to verify by inspection, and
every confidence interval is checked against an independently stated Wilson
formula rather than against whatever the code happens to produce.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from msa_ad.gage_rr import wilson_interval
from msa_ad.seed_faults import (
    FaultCatalogueError,
    analyse_seeded_faults,
    compare_claimed_coverage,
)


def make_catalogue(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "fault_id",
            "hazard_id",
            "hazard_class",
            "injection_point",
            "expected_detection",
        ],
    )


def make_results(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["fault_id", "detected"])


# A deliberately small, fully countable campaign.
#
#   class A: 4 seeded, 3 detected  (F-A1 escapes)
#   class B: 3 seeded, 3 detected
#   class C: 2 seeded, 0 detected
#   -> overall 6 detected of 9 expected
#
# plus one fault marked expected_detection = False that was detected anyway,
# and one catalogued fault never executed.
CATALOGUE = make_catalogue(
    [
        ("F-A1", "HZ-A", "classA", "sensor", True),
        ("F-A2", "HZ-A", "classA", "sensor", True),
        ("F-A3", "HZ-A2", "classA", "fusion", True),
        ("F-A4", "HZ-A2", "classA", "fusion", True),
        ("F-B1", "HZ-B", "classB", "planner", True),
        ("F-B2", "HZ-B", "classB", "planner", True),
        ("F-B3", "HZ-B2", "classB", "planner", True),
        ("F-C1", "HZ-C", "classC", "brake", True),
        ("F-C2", "HZ-C", "classC", "brake", True),
        ("F-X1", "HZ-X", "classA", "sensor", False),  # not claimed
        ("F-P1", "HZ-P", "classB", "planner", True),  # never executed
    ]
)

RESULTS = make_results(
    [
        ("F-A1", False),
        ("F-A2", True),
        ("F-A3", True),
        ("F-A4", True),
        ("F-B1", True),
        ("F-B2", True),
        ("F-B3", True),
        ("F-C1", False),
        ("F-C2", False),
        ("F-X1", True),
    ]
)


@pytest.fixture
def res():
    return analyse_seeded_faults(CATALOGUE, RESULTS, threshold=0.80)


class TestCoverageValidityRatio:
    def test_counts(self, res):
        assert res.n_catalogue == 11
        assert res.n_seeded == 10  # executed
        assert res.n_expected == 9  # executed AND expected to be detected
        assert res.n_detected == 6

    def test_ratio(self, res):
        assert res.detection_rate == pytest.approx(6 / 9)

    def test_wilson_ci_matches_independent_formula(self, res):
        z = 1.959963984540054
        x, n = 6, 9
        p = x / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
        assert res.detection_ci[0] == pytest.approx(centre - half, rel=1e-12)
        assert res.detection_ci[1] == pytest.approx(centre + half, rel=1e-12)

    def test_ci_is_not_the_normal_approximation(self, res):
        # The Wald interval for 6/9 is 0.6667 +/- 1.96*sqrt(pq/n) =
        # (0.3587, 0.9746). Wilson must differ from it.
        p, n = 6 / 9, 9
        half = 1.959963984540054 * math.sqrt(p * (1 - p) / n)
        assert res.detection_ci[0] != pytest.approx(p - half, abs=1e-3)
        assert res.detection_ci[1] != pytest.approx(p + half, abs=1e-3)

    def test_unexecuted_excluded_from_denominator(self, res):
        assert list(res.not_executed["fault_id"]) == ["F-P1"]
        # 9, not 10: the never-executed fault is neither detected nor escaped.
        assert res.n_expected == 9

    def test_unclaimed_fault_excluded_from_denominator(self, res):
        assert list(res.unexpected_detections["fault_id"]) == ["F-X1"]
        assert "F-X1" not in set(res.by_hazard_class["hazard_class"])
        total = int(res.by_hazard_class["seeded"].sum())
        assert total == 9

    def test_escapes_listed(self, res):
        assert set(res.escapes["fault_id"]) == {"F-A1", "F-C1", "F-C2"}


class TestPerHazardClass:
    def test_breakdown_counts(self, res):
        t = res.by_hazard_class.set_index("hazard_class")
        assert (t.loc["classA", "seeded"], t.loc["classA", "detected"]) == (4, 3)
        assert (t.loc["classB", "seeded"], t.loc["classB", "detected"]) == (3, 3)
        assert (t.loc["classC", "seeded"], t.loc["classC", "detected"]) == (2, 0)
        assert t.loc["classA", "escaped"] == 1
        assert t.loc["classC", "escaped"] == 2

    def test_breakdown_rates(self, res):
        t = res.by_hazard_class.set_index("hazard_class")
        assert t.loc["classA", "detection_rate"] == pytest.approx(0.75)
        assert t.loc["classB", "detection_rate"] == pytest.approx(1.0)
        assert t.loc["classC", "detection_rate"] == pytest.approx(0.0)

    def test_breakdown_cis(self, res):
        t = res.by_hazard_class.set_index("hazard_class")
        for cls, x, n in [("classA", 3, 4), ("classB", 3, 3), ("classC", 0, 2)]:
            lo, hi = wilson_interval(x, n)
            assert t.loc[cls, "ci_low"] == pytest.approx(lo)
            assert t.loc[cls, "ci_high"] == pytest.approx(hi)

    def test_zero_detection_class_has_nonzero_upper_bound(self, res):
        # 0/2 must not produce a degenerate [0, 0] interval.
        t = res.by_hazard_class.set_index("hazard_class")
        assert t.loc["classC", "ci_low"] == pytest.approx(0.0)
        assert t.loc["classC", "ci_high"] > 0.5

    def test_perfect_class_has_upper_bound_of_one(self, res):
        t = res.by_hazard_class.set_index("hazard_class")
        assert t.loc["classB", "ci_high"] == pytest.approx(1.0)
        assert t.loc["classB", "ci_low"] < 1.0


class TestFlagging:
    def test_all_three_classes_flagged_at_080(self, res):
        # classA: 3/4, CI low = 0.3006 < 0.8   -> flagged
        # classB: 3/3, CI low = 0.4385 < 0.8   -> flagged (too few faults)
        # classC: 0/2, CI low = 0.0    < 0.8   -> flagged
        assert set(res.flagged_classes["hazard_class"]) == {
            "classA",
            "classB",
            "classC",
        }
        assert res.any_flagged is True

    def test_flag_reasons_distinguish_capability_from_sample_size(self, res):
        t = res.flagged_classes.set_index("hazard_class")
        assert "below threshold" in t.loc["classA", "reason"]
        assert "sample too small" in t.loc["classB", "reason"]
        assert "below threshold" in t.loc["classC", "reason"]

    def test_threshold_zero_flags_nothing(self):
        r = analyse_seeded_faults(CATALOGUE, RESULTS, threshold=0.0)
        assert r.flagged_classes.empty
        assert r.any_flagged is False

    def test_higher_threshold_flags_at_least_as_much(self):
        low = analyse_seeded_faults(CATALOGUE, RESULTS, threshold=0.2)
        high = analyse_seeded_faults(CATALOGUE, RESULTS, threshold=0.9)
        assert set(low.flagged_classes["hazard_class"]) <= set(
            high.flagged_classes["hazard_class"]
        )

    def test_large_clean_class_is_not_flagged(self):
        cat = make_catalogue(
            [(f"F-{i}", "HZ-1", "big", "sensor", True) for i in range(100)]
        )
        res_ = make_results([(f"F-{i}", True) for i in range(100)])
        r = analyse_seeded_faults(cat, res_, threshold=0.80)
        assert r.flagged_classes.empty
        assert r.by_hazard_class.loc[0, "ci_low"] > 0.9


class TestConfidenceLevel:
    def test_ninety_percent_is_narrower(self):
        a = analyse_seeded_faults(CATALOGUE, RESULTS, confidence=0.95)
        b = analyse_seeded_faults(CATALOGUE, RESULTS, confidence=0.90)
        assert b.detection_ci[0] > a.detection_ci[0]
        assert b.detection_ci[1] < a.detection_ci[1]


class TestClaimedVersusValidated:
    def test_all_hazards_claimed(self, res):
        cmp = compare_claimed_coverage(res, 0.95)
        assert cmp.n_detected == 6
        assert cmp.n_expected == 9
        assert cmp.measured_rate == pytest.approx(6 / 9)
        assert cmp.discrepancy == pytest.approx(0.95 - 6 / 9)

    def test_claim_outside_interval_is_reported(self, res):
        cmp = compare_claimed_coverage(res, 0.99)
        assert cmp.claim_within_ci is False

    def test_claim_inside_interval_is_reported(self, res):
        cmp = compare_claimed_coverage(res, 0.70)
        lo, hi = cmp.measured_ci
        assert lo <= 0.70 <= hi
        assert cmp.claim_within_ci is True

    def test_subset_of_hazards(self, res):
        # Restricting to classB's hazards gives a perfect measured rate.
        cmp = compare_claimed_coverage(res, 0.95, claimed_hazard_ids=["HZ-B", "HZ-B2"])
        assert cmp.n_expected == 3
        assert cmp.n_detected == 3
        assert cmp.measured_rate == pytest.approx(1.0)
        assert cmp.discrepancy == pytest.approx(-0.05)

    def test_hazards_claimed_without_measurable_faults(self, res):
        cmp = compare_claimed_coverage(res, 0.95, claimed_hazard_ids=["HZ-A", "HZ-Z"])
        assert cmp.hazards_claimed_without_faults == ["HZ-Z"]
        assert cmp.n_hazards_claimed == 2
        assert cmp.n_hazards_with_seeded_faults == 1

    def test_unexecuted_hazard_counts_as_unmeasured(self, res):
        # HZ-P's only fault was never executed.
        cmp = compare_claimed_coverage(res, 0.95)
        assert "HZ-P" in cmp.hazards_claimed_without_faults
        # HZ-X's only fault is expected_detection = False.
        assert "HZ-X" in cmp.hazards_claimed_without_faults

    def test_per_class_discrepancies(self, res):
        cmp = compare_claimed_coverage(res, 0.90)
        t = cmp.by_hazard_class.set_index("hazard_class")
        assert t.loc["classA", "discrepancy"] == pytest.approx(0.90 - 0.75)
        assert t.loc["classB", "discrepancy"] == pytest.approx(0.90 - 1.0)
        assert t.loc["classC", "discrepancy"] == pytest.approx(0.90 - 0.0)

    def test_invalid_claim_rejected(self, res):
        with pytest.raises(ValueError, match="fraction in"):
            compare_claimed_coverage(res, 95.0)


class TestBooleanCoercion:
    def test_string_booleans_accepted(self):
        cat = make_catalogue(
            [
                ("F1", "H1", "c", "p", "true"),
                ("F2", "H1", "c", "p", "TRUE"),
                ("F3", "H1", "c", "p", "False"),
            ]
        )
        res_ = make_results([("F1", "yes"), ("F2", "no"), ("F3", "yes")])
        r = analyse_seeded_faults(cat, res_)
        assert r.n_expected == 2
        assert r.n_detected == 1
        assert list(r.unexpected_detections["fault_id"]) == ["F3"]

    def test_zero_one_accepted(self):
        cat = make_catalogue([("F1", "H1", "c", "p", 1), ("F2", "H1", "c", "p", 1)])
        res_ = make_results([("F1", 1), ("F2", 0)])
        r = analyse_seeded_faults(cat, res_)
        assert r.detection_rate == pytest.approx(0.5)

    def test_nonsense_boolean_rejected(self):
        cat = make_catalogue([("F1", "H1", "c", "p", "maybe")])
        res_ = make_results([("F1", True)])
        with pytest.raises(FaultCatalogueError, match="must be boolean"):
            analyse_seeded_faults(cat, res_)

    def test_out_of_range_numeric_rejected(self):
        cat = make_catalogue([("F1", "H1", "c", "p", 2)])
        res_ = make_results([("F1", True)])
        with pytest.raises(FaultCatalogueError, match="must be boolean"):
            analyse_seeded_faults(cat, res_)
