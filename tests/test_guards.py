"""Tests for the input guards.

The binary-data guard is the most important of these. A functional-safety
engineer reading this repository will check that passing pass/fail verdicts
to the continuous ANOVA path fails loudly rather than silently producing a
%GRR number that means nothing.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from msa_ad import datagen
from msa_ad.gage_rr import (
    BinaryDataError,
    UnbalancedDesignError,
    attribute_agreement,
    bias_linearity_study,
    gage_rr_anova,
    looks_binary,
)
from msa_ad.report import (
    render_attribute_report,
    render_bias_report,
    render_coverage_claim_report,
    render_gage_rr_report,
    render_seeded_fault_report,
)
from msa_ad.seed_faults import (
    FaultCatalogueError,
    analyse_seeded_faults,
    compare_claimed_coverage,
)


def frame(values, col="value") -> pd.DataFrame:
    """Build a balanced 4 x 3 x 3 long frame from a flat sequence."""
    rows = []
    it = iter(values)
    for i, j, k in itertools.product(range(4), range(3), range(3)):
        rows.append(
            {
                "scenario_id": f"S{i}",
                "bench_id": f"B{j}",
                "replicate": k,
                col: next(it),
            }
        )
    return pd.DataFrame(rows)


N = 4 * 3 * 3


# ---------------------------------------------------------------------------
# The binary-data guard
# ---------------------------------------------------------------------------


class TestBinaryDataGuard:
    @pytest.mark.parametrize(
        "values",
        [
            pytest.param([i % 2 for i in range(N)], id="zero_one_int"),
            pytest.param([float(i % 2) for i in range(N)], id="zero_one_float"),
            pytest.param([bool(i % 2) for i in range(N)], id="bool"),
            pytest.param(
                ["pass" if i % 2 else "fail" for i in range(N)], id="pass_fail_str"
            ),
            pytest.param(
                ["PASS" if i % 2 else "FAIL" for i in range(N)], id="upper_str"
            ),
            pytest.param([1 for _ in range(N)], id="constant"),
            pytest.param([7 if i % 2 else 9 for i in range(N)], id="two_valued_int"),
        ],
    )
    def test_binary_like_input_raises(self, values):
        with pytest.raises(BinaryDataError):
            gage_rr_anova(frame(values))

    def test_message_names_the_column(self):
        with pytest.raises(BinaryDataError, match="'value'"):
            gage_rr_anova(frame([i % 2 for i in range(N)]))

    def test_message_points_to_the_attribute_path(self):
        with pytest.raises(BinaryDataError, match=r"attribute_agreement\(\)"):
            gage_rr_anova(frame([i % 2 for i in range(N)]))

    def test_message_explains_why_not_just_that(self):
        with pytest.raises(BinaryDataError) as exc:
            gage_rr_anova(frame(["pass" if i % 2 else "fail" for i in range(N)]))
        msg = str(exc.value)
        # It must say what is wrong, not merely that something is wrong.
        assert "ndc" in msg
        assert "%GRR" in msg
        assert "nominal category" in msg
        assert "Bernoulli" in msg
        assert "allow_low_cardinality" in msg

    def test_error_is_a_valueerror_subclass(self):
        # So that callers with a broad `except ValueError` still catch it.
        assert issubclass(BinaryDataError, ValueError)

    def test_escape_hatch_allows_low_cardinality_numeric(self):
        values = [7 if i % 2 else 9 for i in range(N)]
        res = gage_rr_anova(frame(values), allow_low_cardinality=True)
        assert res.n_scenarios == 4

    def test_escape_hatch_still_rejects_non_numeric(self):
        values = ["pass" if i % 2 else "fail" for i in range(N)]
        with pytest.raises(TypeError, match="not numeric"):
            gage_rr_anova(frame(values), allow_low_cardinality=True)

    def test_genuinely_continuous_data_passes(self):
        rng = np.random.default_rng(0)
        res = gage_rr_anova(frame(rng.normal(0, 1, N).tolist()))
        assert res.pct_grr > 0

    def test_three_valued_data_is_not_treated_as_binary(self):
        values = [(i % 3) * 1.5 for i in range(N)]
        res = gage_rr_anova(frame(values))
        assert res.n_scenarios == 4

    def test_the_example_data_triggers_the_guard(self):
        runs = datagen.generate_bench_runs()
        with pytest.raises(BinaryDataError):
            gage_rr_anova(runs, value_col="verdict")

    def test_the_example_continuous_column_does_not(self):
        runs = datagen.generate_bench_runs()
        res = gage_rr_anova(runs, value_col="min_ttc_s")
        assert res.n_scenarios == 15


class TestLooksBinary:
    @pytest.mark.parametrize(
        "values, expected",
        [
            ([0, 1, 0, 1], True),
            ([True, False], True),
            (["pass", "fail"], True),
            (["a", "b", "c"], True),  # non-numeric is categorical
            ([1.0, 1.0, 1.0], True),  # single value
            ([1.0, 2.5, 3.7, 9.1], False),
            ([0.0, 0.5, 1.0], False),
        ],
    )
    def test_detection(self, values, expected):
        assert looks_binary(values) is expected

    def test_empty_is_not_binary(self):
        assert looks_binary([]) is False


# ---------------------------------------------------------------------------
# Design guards
# ---------------------------------------------------------------------------


class TestDesignGuards:
    def test_single_bench_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        df = df[df["bench_id"] == "B0"]
        with pytest.raises(UnbalancedDesignError, match="at least 2"):
            gage_rr_anova(df)

    def test_single_scenario_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        df = df[df["scenario_id"] == "S0"]
        with pytest.raises(UnbalancedDesignError, match="at least 2"):
            gage_rr_anova(df)

    def test_single_replicate_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        df = df[df["replicate"] == 0]
        with pytest.raises(UnbalancedDesignError, match="at least 2 replicates"):
            gage_rr_anova(df)

    def test_empty_cell_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        df = df[~((df["scenario_id"] == "S0") & (df["bench_id"] == "B0"))]
        with pytest.raises(UnbalancedDesignError, match="empty cell"):
            gage_rr_anova(df)

    def test_unbalanced_replicates_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        df = df.drop(df.index[0])
        with pytest.raises(UnbalancedDesignError, match="unbalanced|empty cell"):
            gage_rr_anova(df)

    def test_missing_column_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        with pytest.raises(KeyError, match="not_here"):
            gage_rr_anova(df, value_col="not_here")

    def test_nan_measurement_rejected(self):
        vals = np.random.default_rng(1).normal(0, 1, N).tolist()
        vals[3] = float("nan")
        with pytest.raises(UnbalancedDesignError, match="missing values"):
            gage_rr_anova(frame(vals))

    def test_bad_pool_option_rejected(self):
        df = frame(np.random.default_rng(1).normal(0, 1, N).tolist())
        with pytest.raises(ValueError, match="pool_interaction"):
            gage_rr_anova(df, pool_interaction="sometimes")


class TestAttributeGuards:
    def test_more_than_two_categories_rejected(self):
        df = frame(["pass", "fail", "error"] * (N // 3), col="verdict")
        with pytest.raises(ValueError, match="binary verdict"):
            attribute_agreement(df, verdict_col="verdict")

    def test_single_bench_rejected(self):
        df = frame(["pass" if i % 2 else "fail" for i in range(N)], col="verdict")
        df = df[df["bench_id"] == "B0"]
        with pytest.raises(UnbalancedDesignError, match="at least 2 benches"):
            attribute_agreement(df, verdict_col="verdict")

    def test_unbalanced_rejected(self):
        df = frame(["pass" if i % 2 else "fail" for i in range(N)], col="verdict")
        df = df.drop(df.index[0])
        with pytest.raises(UnbalancedDesignError, match="balanced"):
            attribute_agreement(df, verdict_col="verdict")

    def test_missing_column_rejected(self):
        df = frame(["pass"] * N, col="verdict")
        with pytest.raises(KeyError, match="nope"):
            attribute_agreement(df, verdict_col="nope")

    def test_single_replicate_is_allowed(self):
        # Reproducibility is still measurable with one run per bench, even
        # though repeatability is not.
        rows = [
            {"scenario_id": f"S{i}", "bench_id": b, "verdict": v}
            for i, (v1, v2) in enumerate([("pass", "pass"), ("pass", "fail")])
            for b, v in (("B0", v1), ("B1", v2))
        ]
        res = attribute_agreement(pd.DataFrame(rows))
        assert res.n_replicates == 1
        assert res.within_bench_overall[2] == pytest.approx(1.0)
        assert res.between_bench_strict[2] == pytest.approx(0.5)


class TestSeedFaultGuards:
    def test_missing_catalogue_column_rejected(self):
        cat = pd.DataFrame({"fault_id": ["F1"], "hazard_id": ["H1"]})
        res = pd.DataFrame({"fault_id": ["F1"], "detected": [True]})
        with pytest.raises(FaultCatalogueError, match="missing required column"):
            analyse_seeded_faults(cat, res)

    def test_missing_results_column_rejected(self):
        cat = pd.DataFrame(
            {
                "fault_id": ["F1"],
                "hazard_id": ["H1"],
                "hazard_class": ["c"],
                "injection_point": ["p"],
                "expected_detection": [True],
            }
        )
        with pytest.raises(FaultCatalogueError, match="missing required column"):
            analyse_seeded_faults(cat, pd.DataFrame({"fault_id": ["F1"]}))

    def test_duplicate_fault_id_rejected(self):
        cat = pd.DataFrame(
            {
                "fault_id": ["F1", "F1"],
                "hazard_id": ["H1", "H1"],
                "hazard_class": ["c", "c"],
                "injection_point": ["p", "p"],
                "expected_detection": [True, True],
            }
        )
        res = pd.DataFrame({"fault_id": ["F1"], "detected": [True]})
        with pytest.raises(FaultCatalogueError, match="duplicate fault_id"):
            analyse_seeded_faults(cat, res)

    def test_result_for_unknown_fault_rejected(self):
        cat = pd.DataFrame(
            {
                "fault_id": ["F1"],
                "hazard_id": ["H1"],
                "hazard_class": ["c"],
                "injection_point": ["p"],
                "expected_detection": [True],
            }
        )
        res = pd.DataFrame({"fault_id": ["F1", "F9"], "detected": [True, True]})
        with pytest.raises(FaultCatalogueError, match="absent from"):
            analyse_seeded_faults(cat, res)

    def test_invalid_threshold_rejected(self):
        cat = pd.DataFrame(
            {
                "fault_id": ["F1"],
                "hazard_id": ["H1"],
                "hazard_class": ["c"],
                "injection_point": ["p"],
                "expected_detection": [True],
            }
        )
        res = pd.DataFrame({"fault_id": ["F1"], "detected": [True]})
        with pytest.raises(ValueError, match="threshold"):
            analyse_seeded_faults(cat, res, threshold=1.5)


class TestBiasGuards:
    def test_too_few_observations_rejected(self):
        df = pd.DataFrame({"reference_value": [1.0, 2.0], "value": [1.1, 2.1]})
        with pytest.raises(ValueError, match="at least 3"):
            bias_linearity_study(df)

    def test_single_reference_level_rejected(self):
        df = pd.DataFrame({"reference_value": [1.0] * 5, "value": [1.1] * 5})
        with pytest.raises(ValueError, match="two distinct reference"):
            bias_linearity_study(df)


class TestWilsonGuards:
    def test_successes_above_n_rejected(self):
        from msa_ad import wilson_interval

        with pytest.raises(ValueError, match=r"must be in \[0, n\]"):
            wilson_interval(11, 10)

    def test_negative_successes_rejected(self):
        from msa_ad import wilson_interval

        with pytest.raises(ValueError, match=r"must be in \[0, n\]"):
            wilson_interval(-1, 10)

    def test_invalid_confidence_rejected(self):
        from msa_ad import wilson_interval

        with pytest.raises(ValueError, match="confidence"):
            wilson_interval(5, 10, confidence=1.5)


# ---------------------------------------------------------------------------
# Reproducibility and end-to-end smoke tests
# ---------------------------------------------------------------------------


class TestDatagenReproducibility:
    def test_bench_runs_are_deterministic(self):
        a = datagen.generate_bench_runs(datagen.DEFAULT_SEED)
        b = datagen.generate_bench_runs(datagen.DEFAULT_SEED)
        pd.testing.assert_frame_equal(a, b)

    def test_catalogue_and_results_are_deterministic(self):
        c1 = datagen.generate_fault_catalogue()
        c2 = datagen.generate_fault_catalogue()
        pd.testing.assert_frame_equal(c1, c2)
        pd.testing.assert_frame_equal(
            datagen.generate_campaign_results(c1),
            datagen.generate_campaign_results(c2),
        )

    def test_different_seed_gives_different_data(self):
        a = datagen.generate_bench_runs(1)
        b = datagen.generate_bench_runs(2)
        assert not a["min_ttc_s"].equals(b["min_ttc_s"])

    def test_verdict_is_consistent_with_the_metric(self):
        runs = datagen.generate_bench_runs()
        expected = np.where(
            runs["min_ttc_s"] >= datagen.TTC_PASS_THRESHOLD_S, "pass", "fail"
        )
        # The stored metric is rounded to 4 dp, so allow the rare row whose
        # rounding straddles the threshold.
        assert (runs["verdict"].to_numpy() == expected).mean() > 0.99

    def test_hazard_class_detection_counts_are_exact(self):
        cat = datagen.generate_fault_catalogue()
        res = datagen.generate_campaign_results(cat)
        merged = cat.merge(res, on="fault_id")
        merged = merged[
            merged["expected_detection"]
            & ~merged["fault_id"].str.startswith("F-PEND")
        ]
        counts = merged.groupby("hazard_class")["detected"].agg(["size", "sum"])
        for hazard_class, spec in datagen.HAZARD_CLASSES.items():
            assert counts.loc[hazard_class, "size"] == spec["seeded"]
            assert counts.loc[hazard_class, "sum"] == spec["detected"]


class TestExampleDataContainsFindings:
    """The bundled example must actually find something."""

    def test_one_bench_is_materially_worse(self):
        runs = datagen.generate_bench_runs()
        res = gage_rr_anova(runs, value_col="min_ttc_s")
        table = res.per_bench_repeatability
        assert table["sd_ratio_vs_best"].max() > 2.0

    def test_grr_is_not_acceptable(self):
        runs = datagen.generate_bench_runs()
        res = gage_rr_anova(runs, value_col="min_ttc_s")
        assert res.verdict != "acceptable"
        assert res.ndc < 5

    def test_benches_disagree_on_some_verdicts(self):
        runs = datagen.generate_bench_runs()
        res = attribute_agreement(runs, verdict_col="verdict")
        assert res.between_bench_strict[2] < 1.0
        assert not res.disagreement_scenarios.empty

    def test_one_hazard_class_detects_poorly(self):
        cat = datagen.generate_fault_catalogue()
        res = datagen.generate_campaign_results(cat)
        analysis = analyse_seeded_faults(cat, res, threshold=0.80)
        assert analysis.any_flagged
        t = analysis.by_hazard_class.set_index("hazard_class")
        assert t.loc["perception_false_negative", "detection_rate"] < 0.7

    def test_claimed_coverage_is_not_supported(self):
        cat = datagen.generate_fault_catalogue()
        res = datagen.generate_campaign_results(cat)
        analysis = analyse_seeded_faults(cat, res)
        cmp = compare_claimed_coverage(analysis, 0.95)
        assert cmp.claim_within_ci is False
        assert cmp.discrepancy > 0


class TestReportsRender:
    """Reports must produce non-empty text and stay inside the page width."""

    def _check(self, text: str) -> None:
        assert text.strip()
        over = [ln for ln in text.splitlines() if len(ln) > 100]
        assert not over, f"lines exceed 100 chars: {over[:2]}"

    def test_gage_rr_report(self):
        runs = datagen.generate_bench_runs()
        text = render_gage_rr_report(gage_rr_anova(runs, value_col="min_ttc_s"))
        self._check(text)
        assert "%GRR" in text and "ndc" in text

    def test_gage_rr_report_with_tolerance(self):
        runs = datagen.generate_bench_runs()
        text = render_gage_rr_report(
            gage_rr_anova(runs, value_col="min_ttc_s", tolerance=2.0)
        )
        self._check(text)
        assert "tolerance" in text

    def test_attribute_report(self):
        runs = datagen.generate_bench_runs()
        text = render_attribute_report(attribute_agreement(runs, verdict_col="verdict"))
        self._check(text)
        assert "Fleiss" in text
        # It must not report a %GRR *value* for binary data. The prose does
        # mention %GRR in order to say it is deliberately absent.
        assert "%GRR =" not in text
        assert "ndc  =" not in text
        assert "There is no %GRR" in text

    def test_seeded_fault_report(self):
        cat = datagen.generate_fault_catalogue()
        res = datagen.generate_campaign_results(cat)
        text = render_seeded_fault_report(analyse_seeded_faults(cat, res))
        self._check(text)
        assert "COVERAGE-VALIDITY RATIO" in text

    def test_coverage_claim_report(self):
        cat = datagen.generate_fault_catalogue()
        res = datagen.generate_campaign_results(cat)
        analysis = analyse_seeded_faults(cat, res)
        text = render_coverage_claim_report(compare_claimed_coverage(analysis, 0.95))
        self._check(text)
        assert "Discrepancy" in text

    def test_bias_report(self):
        rng = np.random.default_rng(5)
        ref = np.repeat(np.arange(1.0, 6.0), 8)
        df = pd.DataFrame(
            {"reference_value": ref, "value": ref + 0.2 + rng.normal(0, 0.05, ref.size)}
        )
        text = render_bias_report(bias_linearity_study(df))
        self._check(text)
        assert "LINEARITY" in text
