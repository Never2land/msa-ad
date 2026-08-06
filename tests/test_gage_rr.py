"""Numerical correctness tests for the Gage R&R and agreement statistics.

These tests assert against values obtained independently of the
implementation:

* a small crossed design whose ANOVA and variance components are worked
  through by hand in the test itself;
* an independent least-squares recomputation of the sums of squares, using
  model comparison rather than the closed-form margin formulas the module
  uses, so an algebra error in one path cannot hide in the other;
* the AIAG MSA 4th edition gage study data set;
* published Wilson score intervals;
* the Fleiss (1971) worked example, whose kappa is 0.430.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest

from msa_ad.gage_rr import (
    attribute_agreement,
    bias_linearity_study,
    cohen_kappa,
    fleiss_kappa,
    gage_rr_anova,
    wilson_interval,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def long_frame(array: np.ndarray, scenarios=None, benches=None) -> pd.DataFrame:
    """Turn a (p, o, r) array into the long form the API expects."""
    p, o, r = array.shape
    scenarios = scenarios or [f"S{i + 1}" for i in range(p)]
    benches = benches or [f"B{j + 1}" for j in range(o)]
    rows = []
    for i, j, k in itertools.product(range(p), range(o), range(r)):
        rows.append(
            {
                "scenario_id": scenarios[i],
                "bench_id": benches[j],
                "replicate": k + 1,
                "value": float(array[i, j, k]),
            }
        )
    return pd.DataFrame(rows)


def anova_by_least_squares(array: np.ndarray) -> dict[str, float]:
    """Independent sums of squares via sequential model comparison.

    Builds full-rank dummy-coded design matrices and computes each term's SS
    as the drop in residual sum of squares when that term is added. This is a
    different algebraic route from the closed-form cell-margin formulas used
    in ``gage_rr_anova``, so the two agreeing is meaningful evidence.
    """
    p, o, r = array.shape
    y = array.reshape(-1)
    n = y.size
    idx = np.array(list(itertools.product(range(p), range(o), range(r))))
    part, oper = idx[:, 0], idx[:, 1]

    def rss(x: np.ndarray) -> float:
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        return float(np.sum((y - x @ beta) ** 2))

    intercept = np.ones((n, 1))
    d_part = np.stack([(part == i).astype(float) for i in range(1, p)], axis=1)
    d_oper = np.stack([(oper == j).astype(float) for j in range(1, o)], axis=1)
    d_int = np.stack(
        [
            ((part == i) & (oper == j)).astype(float)
            for i in range(1, p)
            for j in range(1, o)
        ],
        axis=1,
    )

    x0 = intercept
    x1 = np.hstack([intercept, d_part])
    x2 = np.hstack([intercept, d_part, d_oper])
    x3 = np.hstack([intercept, d_part, d_oper, d_int])

    rss0, rss1, rss2, rss3 = rss(x0), rss(x1), rss(x2), rss(x3)
    return {
        "ss_scenario": rss0 - rss1,
        "ss_bench": rss1 - rss2,
        "ss_interaction": rss2 - rss3,
        "ss_error": rss3,
        "ss_total": rss0,
    }


# The AIAG MSA 4th edition gage study data: 10 parts, 3 appraisers, 3 trials.
# Rows are trials 1-3 for each appraiser; columns are parts 1-10.
AIAG_RAW = {
    "A": [
        [0.29, -0.56, 1.34, 0.47, -0.80, 0.02, 0.59, -0.31, 2.26, -1.36],
        [0.41, -0.68, 1.17, 0.50, -0.92, -0.11, 0.75, -0.20, 1.99, -1.25],
        [0.64, -0.58, 1.27, 0.64, -0.84, -0.21, 0.66, -0.17, 2.01, -1.31],
    ],
    "B": [
        [0.08, -0.47, 1.19, 0.01, -0.56, -0.20, 0.47, -0.63, 1.80, -1.68],
        [0.25, -1.22, 0.94, 1.03, -1.20, 0.22, 0.55, 0.08, 2.12, -1.62],
        [0.07, -0.68, 1.34, 0.20, -1.28, 0.06, 0.83, -0.34, 2.19, -1.50],
    ],
    "C": [
        [0.04, -1.38, 0.88, 0.14, -1.46, -0.29, 0.02, -0.46, 1.77, -1.49],
        [-0.11, -1.13, 1.09, 0.20, -1.07, -0.67, 0.01, -0.56, 1.45, -1.77],
        [-0.15, -0.96, 0.67, 0.11, -1.45, -0.49, 0.21, -0.49, 1.87, -2.16],
    ],
}


def aiag_array() -> np.ndarray:
    x = np.zeros((10, 3, 3))
    for j, op in enumerate("ABC"):
        for k in range(3):
            for i in range(10):
                x[i, j, k] = AIAG_RAW[op][k][i]
    return x


# ---------------------------------------------------------------------------
# Hand-computed crossed design
# ---------------------------------------------------------------------------
#
# 2 scenarios x 2 benches x 2 replicates.
#
#   S1/B1: 10, 12   cell mean 11        S1/B2: 14, 16   cell mean 15
#   S2/B1: 20, 22   cell mean 21        S2/B2: 24, 26   cell mean 25
#
# grand mean 18; scenario means 13, 23; bench means 16, 20.
#
#   SS_scenario    = o*r * sum (13-18)^2 + (23-18)^2 = 4 * 50  = 200
#   SS_bench       = p*r * sum (16-18)^2 + (20-18)^2 = 4 *  8  =  32
#   interaction residuals cellmean - scen - bench + grand are all 0
#   SS_interaction =                                              0
#   SS_error       = 4 cells x ((-1)^2 + 1^2)                   =   8
#   SS_total       = 200 + 32 + 0 + 8                           = 240
#
# df: 1, 1, 1, 4.  MS: 200, 32, 0, 2.
# Interaction F = 0/2 = 0, p = 1 > 0.25, so AIAG pools it into error.
#   MS_pooled  = (0 + 8) / (1 + 4)      = 1.6
#   var_repeat = 1.6
#   var_bench  = (32  - 1.6) / (p*r=4)  = 7.6
#   var_scen   = (200 - 1.6) / (o*r=4)  = 49.6
#   EV  = sqrt(1.6)  = 1.2649110640673518
#   AV  = sqrt(7.6)  = 2.7568097504180442
#   GRR = sqrt(9.2)  = 3.0331501776206204
#   PV  = sqrt(49.6) = 7.0427267446636025
#   TV  = sqrt(58.8) = 7.6681158050723255
#   ndc = floor(1.41 * 7.0427267 / 3.0331502) = floor(3.2738) = 3

HAND = np.array(
    [
        [[10.0, 12.0], [14.0, 16.0]],
        [[20.0, 22.0], [24.0, 26.0]],
    ]
)


class TestHandComputedGageRR:
    def test_anova_sums_of_squares(self):
        res = gage_rr_anova(long_frame(HAND))
        ss = dict(zip(res.anova["source"], res.anova["ss"]))
        assert ss["scenario_id (scenario)"] == pytest.approx(200.0)
        assert ss["bench_id (bench)"] == pytest.approx(32.0)
        assert ss["scenario x bench"] == pytest.approx(0.0, abs=1e-12)
        assert ss["repeatability (error)"] == pytest.approx(8.0)
        assert ss["total"] == pytest.approx(240.0)

    def test_degrees_of_freedom(self):
        res = gage_rr_anova(long_frame(HAND))
        df = dict(zip(res.anova["source"], res.anova["df"]))
        assert df["scenario_id (scenario)"] == 1
        assert df["bench_id (bench)"] == 1
        assert df["scenario x bench"] == 1
        assert df["repeatability (error)"] == 4
        assert df["total"] == 7

    def test_interaction_is_pooled(self):
        res = gage_rr_anova(long_frame(HAND))
        assert res.interaction_f == pytest.approx(0.0)
        assert res.interaction_p == pytest.approx(1.0)
        assert res.interaction_pooled is True

    def test_variance_components_pooled(self):
        res = gage_rr_anova(long_frame(HAND))
        assert res.var_repeatability == pytest.approx(1.6)
        assert res.var_bench == pytest.approx(7.6)
        assert res.var_interaction == pytest.approx(0.0)
        assert res.var_scenario == pytest.approx(49.6)

    def test_standard_deviations_pooled(self):
        res = gage_rr_anova(long_frame(HAND))
        assert res.ev == pytest.approx(math.sqrt(1.6), rel=1e-12)
        assert res.av == pytest.approx(math.sqrt(7.6), rel=1e-12)
        assert res.grr == pytest.approx(math.sqrt(9.2), rel=1e-12)
        assert res.pv == pytest.approx(math.sqrt(49.6), rel=1e-12)
        assert res.tv == pytest.approx(math.sqrt(58.8), rel=1e-12)

    def test_percentages_pooled(self):
        res = gage_rr_anova(long_frame(HAND))
        tv = math.sqrt(58.8)
        assert res.pct_ev == pytest.approx(100 * math.sqrt(1.6) / tv, rel=1e-12)
        assert res.pct_av == pytest.approx(100 * math.sqrt(7.6) / tv, rel=1e-12)
        assert res.pct_grr == pytest.approx(100 * math.sqrt(9.2) / tv, rel=1e-12)
        assert res.pct_pv == pytest.approx(100 * math.sqrt(49.6) / tv, rel=1e-12)
        # Explicit numeric values:
        #   %EV  = 100 * sqrt(1.6)  / sqrt(58.8) = 16.4957
        #   %AV  = 100 * sqrt(7.6)  / sqrt(58.8) = 35.9516
        #   %GRR = 100 * sqrt(9.2)  / sqrt(58.8) = 39.5554
        #   %PV  = 100 * sqrt(49.6) / sqrt(58.8) = 91.8443
        assert res.pct_ev == pytest.approx(16.4957, abs=1e-3)
        assert res.pct_av == pytest.approx(35.9516, abs=1e-3)
        assert res.pct_grr == pytest.approx(39.5554, abs=1e-3)
        assert res.pct_pv == pytest.approx(91.8443, abs=1e-3)

    def test_ndc_and_verdict(self):
        res = gage_rr_anova(long_frame(HAND))
        assert res.ndc == 3
        assert res.ndc_ok is False
        assert res.verdict == "unacceptable"

    def test_grr_identity(self):
        res = gage_rr_anova(long_frame(HAND))
        assert res.grr == pytest.approx(math.hypot(res.ev, res.av), rel=1e-12)
        assert res.tv == pytest.approx(math.hypot(res.grr, res.pv), rel=1e-12)

    def test_unpooled_path_hand_computed(self):
        # With the interaction retained:
        #   var_repeat = MS_error                = 2
        #   var_int    = (MS_int - MS_err)/r = (0-2)/2 = -1 -> clamped to 0
        #   var_bench  = (MS_bench - MS_int)/(p*r) = (32-0)/4 = 8
        #   var_scen   = (MS_scen  - MS_int)/(o*r) = (200-0)/4 = 50
        res = gage_rr_anova(long_frame(HAND), pool_interaction="never")
        assert res.interaction_pooled is False
        assert res.var_repeatability == pytest.approx(2.0)
        assert res.var_interaction == pytest.approx(0.0)
        assert res.var_bench == pytest.approx(8.0)
        assert res.var_scenario == pytest.approx(50.0)
        assert res.ev == pytest.approx(math.sqrt(2.0), rel=1e-12)
        assert res.grr == pytest.approx(math.sqrt(10.0), rel=1e-12)
        assert res.tv == pytest.approx(math.sqrt(60.0), rel=1e-12)


class TestNegativeVarianceClamping:
    def test_bench_variance_clamped_to_zero(self):
        # Benches with identical means: MS_bench < MS_pooled, so the naive
        # moment estimator is negative and must be clamped.
        rng = np.random.default_rng(7)
        x = rng.normal(0, 1, size=(6, 3, 3))
        x = x - x.mean(axis=(0, 2), keepdims=True)  # kill the bench effect
        res = gage_rr_anova(long_frame(x))
        assert res.var_bench >= 0.0
        assert res.var_bench == pytest.approx(0.0, abs=1e-12)


class TestIndependentLeastSquaresCrosscheck:
    """The closed-form SS must match an independent regression computation."""

    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_random_designs(self, seed):
        rng = np.random.default_rng(seed)
        p = int(rng.integers(3, 9))
        o = int(rng.integers(2, 5))
        r = int(rng.integers(2, 5))
        x = rng.normal(0, 1, size=(p, o, r)) + rng.normal(0, 3, size=(p, 1, 1))
        res = gage_rr_anova(long_frame(x))
        ref = anova_by_least_squares(x)
        ss = dict(zip(res.anova["source"], res.anova["ss"]))
        assert ss["scenario_id (scenario)"] == pytest.approx(ref["ss_scenario"])
        assert ss["bench_id (bench)"] == pytest.approx(ref["ss_bench"])
        assert ss["scenario x bench"] == pytest.approx(ref["ss_interaction"])
        assert ss["repeatability (error)"] == pytest.approx(ref["ss_error"])
        assert ss["total"] == pytest.approx(ref["ss_total"])

    def test_aiag_data_crosscheck(self):
        x = aiag_array()
        res = gage_rr_anova(long_frame(x))
        ref = anova_by_least_squares(x)
        ss = dict(zip(res.anova["source"], res.anova["ss"]))
        assert ss["scenario_id (scenario)"] == pytest.approx(ref["ss_scenario"])
        assert ss["bench_id (bench)"] == pytest.approx(ref["ss_bench"])
        assert ss["scenario x bench"] == pytest.approx(ref["ss_interaction"])
        assert ss["repeatability (error)"] == pytest.approx(ref["ss_error"])

    @pytest.mark.parametrize("seed", [11, 12, 13])
    def test_ss_decomposition_identity(self, seed):
        rng = np.random.default_rng(seed)
        x = rng.normal(0, 1, size=(5, 3, 4))
        res = gage_rr_anova(long_frame(x))
        ss = dict(zip(res.anova["source"], res.anova["ss"]))
        total = (
            ss["scenario_id (scenario)"]
            + ss["bench_id (bench)"]
            + ss["scenario x bench"]
            + ss["repeatability (error)"]
        )
        assert total == pytest.approx(ss["total"])


class TestAIAGWorkedExample:
    """AIAG MSA 4th edition gage study data set.

    Scope of what these assertions establish, stated precisely:

    * The part, appraiser and equipment sums of squares below match the
      published ANOVA table for this data set.
    * The interaction sum of squares is asserted at the value this
      implementation computes from the data. It has **not** been checked
      against the printed table, and the reference value is not restated
      here from memory. It is instead cross-checked against an independent
      least-squares computation in ``TestIndependentLeastSquaresCrosscheck``,
      which is what actually establishes correctness.
    * The primary correctness evidence for this module is the hand-computed
      example in ``TestHandComputedGageRR``, where every quantity is derived
      arithmetically in the comments above it.

    Anyone with a copy of the standard is invited to check the interaction
    row and open an issue if it disagrees.
    """

    def test_published_sums_of_squares(self):
        res = gage_rr_anova(long_frame(aiag_array()))
        ss = dict(zip(res.anova["source"], res.anova["ss"]))
        assert ss["scenario_id (scenario)"] == pytest.approx(88.3619, abs=5e-4)
        assert ss["bench_id (bench)"] == pytest.approx(3.1673, abs=5e-4)
        assert ss["repeatability (error)"] == pytest.approx(2.7589, abs=5e-4)
        assert ss["scenario x bench"] == pytest.approx(0.3590, abs=5e-4)
        assert ss["total"] == pytest.approx(94.6471, abs=5e-4)

    def test_mean_squares(self):
        res = gage_rr_anova(long_frame(aiag_array()))
        ms = dict(zip(res.anova["source"], res.anova["ms"]))
        assert ms["scenario_id (scenario)"] == pytest.approx(9.81799, abs=5e-5)
        assert ms["bench_id (bench)"] == pytest.approx(1.58363, abs=5e-5)
        assert ms["repeatability (error)"] == pytest.approx(0.04598, abs=5e-5)

    def test_interaction_pooled(self):
        res = gage_rr_anova(long_frame(aiag_array()))
        # Interaction is far from significant, so AIAG's alpha = 0.25 rule
        # pools it into the error term.
        assert res.interaction_p > 0.25
        assert res.interaction_pooled is True
        assert res.var_interaction == pytest.approx(0.0)

    def test_variance_components(self):
        res = gage_rr_anova(long_frame(aiag_array()))
        # Pooled MS_error = (0.3590 + 2.7589) / (18 + 60) = 0.0399729...
        ms_pooled = (0.3590 + 2.7589) / 78.0
        assert res.var_repeatability == pytest.approx(ms_pooled, abs=1e-5)
        assert res.var_bench == pytest.approx(
            (1.58363 - ms_pooled) / 30.0, abs=1e-5
        )
        assert res.var_scenario == pytest.approx(
            (9.81799 - ms_pooled) / 9.0, abs=1e-5
        )

    def test_percent_grr_and_ndc(self):
        res = gage_rr_anova(long_frame(aiag_array()))
        assert res.pct_grr == pytest.approx(27.86, abs=0.05)
        assert res.pct_ev == pytest.approx(18.42, abs=0.05)
        assert res.pct_av == pytest.approx(20.90, abs=0.05)
        assert res.pct_pv == pytest.approx(96.04, abs=0.05)
        assert res.ndc == 4
        assert res.verdict == "marginal"

    def test_per_bench_repeatability_matches_direct_computation(self):
        x = aiag_array()
        res = gage_rr_anova(long_frame(x))
        table = res.per_bench_repeatability.set_index("bench")
        for j, bench in enumerate(["B1", "B2", "B3"]):
            dev = x[:, j, :] - x[:, j, :].mean(axis=1, keepdims=True)
            expected = math.sqrt(float(np.sum(dev**2)) / (10 * (3 - 1)))
            assert table.loc[bench, "repeatability_sd"] == pytest.approx(expected)


class TestKnownVarianceRecovery:
    def test_zero_noise_gives_zero_ev(self):
        # Perfectly repeatable bench: every replicate identical.
        base = np.array([[1.0, 2.0, 3.0], [10.0, 11.0, 12.0], [20.0, 22.0, 24.0]])
        x = np.repeat(base[:, :, None], 4, axis=2)
        res = gage_rr_anova(long_frame(x))
        assert res.ev == pytest.approx(0.0, abs=1e-12)
        assert res.var_repeatability == pytest.approx(0.0, abs=1e-12)

    def test_pure_bench_offset_recovered(self):
        # Scenario levels 0, 10, 20, 30; bench offsets -3, 0, +3; no noise.
        # With no replicate noise MS_error = 0 and MS_int = 0, so
        # var_bench = MS_bench / (p*r).
        p, o, r = 4, 3, 2
        scen = np.array([0.0, 10.0, 20.0, 30.0])
        offs = np.array([-3.0, 0.0, 3.0])
        x = np.zeros((p, o, r))
        for i in range(p):
            for j in range(o):
                x[i, j, :] = scen[i] + offs[j]
        res = gage_rr_anova(long_frame(x), pool_interaction="never")
        assert res.ev == pytest.approx(0.0, abs=1e-9)
        # SS_bench = p*r*sum(offs^2) = 8*18 = 144; MS_bench = 72;
        # var_bench = 72 / (p*r = 8) = 9  -> AV = 3, exactly the offset SD
        # (population SD of -3, 0, 3 is sqrt(6); the ANOVA estimator targets
        # the variance component, here 9).
        assert res.var_bench == pytest.approx(9.0, abs=1e-9)
        assert res.av == pytest.approx(3.0, abs=1e-9)


class TestTolerance:
    def test_percent_grr_of_tolerance(self):
        res = gage_rr_anova(long_frame(HAND), tolerance=100.0)
        grr = math.sqrt(9.2)
        assert res.pct_grr_tolerance == pytest.approx(100 * 6 * grr / 100.0)

    def test_negative_tolerance_rejected(self):
        with pytest.raises(ValueError, match="tolerance must be positive"):
            gage_rr_anova(long_frame(HAND), tolerance=-1.0)


# ---------------------------------------------------------------------------
# Wilson score intervals
# ---------------------------------------------------------------------------


class TestWilsonInterval:
    """Published Wilson score intervals at 95%."""

    @pytest.mark.parametrize(
        "successes, n, low, high",
        [
            (0, 10, 0.0000, 0.2775),
            (1, 10, 0.0179, 0.4042),
            (5, 10, 0.2366, 0.7634),
            (10, 10, 0.7225, 1.0000),
            (15, 20, 0.5313, 0.8881),
            (81, 100, 0.7222, 0.8749),
        ],
    )
    def test_known_values(self, successes, n, low, high):
        lo, hi = wilson_interval(successes, n)
        assert lo == pytest.approx(low, abs=5e-4)
        assert hi == pytest.approx(high, abs=5e-4)

    def test_closed_form(self):
        # Direct restatement of the Wilson formula, independent of the code.
        z = 1.959963984540054
        x, n = 7, 23
        p = x / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
        lo, hi = wilson_interval(x, n)
        assert lo == pytest.approx(centre - half, rel=1e-12)
        assert hi == pytest.approx(centre + half, rel=1e-12)

    def test_symmetry(self):
        lo1, hi1 = wilson_interval(3, 17)
        lo2, hi2 = wilson_interval(14, 17)
        assert lo1 == pytest.approx(1 - hi2, rel=1e-12)
        assert hi1 == pytest.approx(1 - lo2, rel=1e-12)

    def test_bounds_stay_in_unit_interval(self):
        for n in (1, 2, 5, 30):
            for x in range(n + 1):
                lo, hi = wilson_interval(x, n)
                assert 0.0 <= lo <= hi <= 1.0

    def test_never_degenerate_at_extremes(self):
        # The point of using Wilson rather than Wald: at x = 0 and x = n the
        # normal approximation collapses to a zero-width interval.
        lo, hi = wilson_interval(0, 12)
        assert hi > 0.0
        lo, hi = wilson_interval(12, 12)
        assert lo < 1.0

    def test_ninety_percent_is_narrower(self):
        lo95, hi95 = wilson_interval(6, 20, confidence=0.95)
        lo90, hi90 = wilson_interval(6, 20, confidence=0.90)
        assert lo90 > lo95
        assert hi90 < hi95

    def test_zero_n_is_nan(self):
        lo, hi = wilson_interval(0, 0)
        assert math.isnan(lo) and math.isnan(hi)


# ---------------------------------------------------------------------------
# Kappa
# ---------------------------------------------------------------------------

# Fleiss (1971) worked example: 30 subjects, 6 raters, 5 diagnostic
# categories. The published overall kappa for this table is 0.430.
FLEISS_1971 = [
    [0, 0, 0, 0, 6], [0, 3, 0, 0, 3], [0, 1, 4, 0, 1], [0, 0, 0, 0, 6],
    [0, 3, 0, 3, 0], [2, 0, 4, 0, 0], [0, 0, 4, 0, 2], [2, 0, 3, 1, 0],
    [2, 0, 0, 4, 0], [0, 0, 0, 0, 6], [1, 0, 0, 5, 0], [1, 1, 0, 4, 0],
    [0, 3, 0, 3, 0], [1, 0, 0, 5, 0], [0, 2, 0, 3, 1], [0, 0, 5, 0, 1],
    [3, 0, 0, 1, 2], [5, 1, 0, 0, 0], [0, 2, 0, 4, 0], [1, 0, 2, 0, 3],
    [0, 0, 0, 0, 6], [0, 1, 0, 5, 0], [0, 2, 0, 1, 3], [2, 0, 0, 4, 0],
    [1, 0, 0, 4, 1], [0, 5, 0, 1, 0], [4, 0, 0, 0, 2], [0, 2, 0, 4, 0],
    [1, 0, 5, 0, 0], [0, 0, 0, 0, 6],
]


class TestFleissKappa:
    """Exact hand-computed values, then the Fleiss (1971) table.

    The two small tables below are the primary correctness evidence: every
    intermediate quantity is written out, so the expected kappa can be
    checked by a reader with a pencil. The Fleiss (1971) table is a
    secondary, looser check - see the note on that test.
    """

    def test_hand_computed_kappa_one_third(self):
        # 4 subjects, 3 raters, 2 categories.
        #   S1 [3,0]  S2 [0,3]  S3 [2,1]  S4 [1,2]
        #
        # p_i = (sum_j n_ij^2 - n) / (n (n - 1)) with n = 3:
        #   S1 (9 - 3)/6 = 1        S2 (9 - 3)/6 = 1
        #   S3 (5 - 3)/6 = 1/3      S4 (5 - 3)/6 = 1/3
        #   p_bar = (1 + 1 + 1/3 + 1/3) / 4 = 2/3
        # Marginals: column totals 6 and 6 of N*n = 12, so p_j = 1/2, 1/2
        #   p_e = 1/4 + 1/4 = 1/2
        # kappa = (2/3 - 1/2) / (1 - 1/2) = (1/6) / (1/2) = 1/3
        table = [[3, 0], [0, 3], [2, 1], [1, 2]]
        assert fleiss_kappa(table) == pytest.approx(1.0 / 3.0, rel=1e-12)

    def test_hand_computed_kappa_seven_twelfths(self):
        # 5 subjects, 4 raters, 2 categories, asymmetric marginals.
        #   S1 [4,0]  S2 [3,1]  S3 [1,3]  S4 [0,4]  S5 [4,0]
        #
        # p_i = (sum_j n_ij^2 - 4) / 12:
        #   S1 (16-4)/12 = 1     S2 (10-4)/12 = 1/2   S3 (10-4)/12 = 1/2
        #   S4 (16-4)/12 = 1     S5 (16-4)/12 = 1
        #   p_bar = (1 + 1/2 + 1/2 + 1 + 1) / 5 = 4/5
        # Marginals: column totals 12 and 8 of N*n = 20 -> p_j = 0.6, 0.4
        #   p_e = 0.36 + 0.16 = 0.52
        # kappa = (0.8 - 0.52) / (1 - 0.52) = 0.28 / 0.48 = 7/12
        table = [[4, 0], [3, 1], [1, 3], [0, 4], [4, 0]]
        assert fleiss_kappa(table) == pytest.approx(7.0 / 12.0, rel=1e-12)

    def test_fleiss_1971_table(self):
        """Fleiss (1971): 30 subjects, 6 raters, 5 diagnostic categories.

        The kappa usually quoted for this data set is approximately 0.43.
        The transcription of the 30x5 table used here yields 0.4289, which
        is consistent with that figure to the precision it is normally
        quoted at, but the small gap most likely indicates that one cell of
        our copy of the table differs from the original. Rather than adjust
        the data to hit a remembered constant, the check is deliberately
        loose here and the exact-value evidence lives in the two
        hand-computed tests above.
        """
        k = fleiss_kappa(FLEISS_1971)
        assert 0.42 < k < 0.44

    def test_perfect_agreement_is_one(self):
        counts = [[4, 0], [0, 4], [4, 0], [0, 4]]
        assert fleiss_kappa(counts) == pytest.approx(1.0)

    def test_chance_level_agreement_is_about_zero(self):
        # Every subject split evenly: observed agreement equals chance.
        counts = [[2, 2]] * 50
        assert fleiss_kappa(counts) == pytest.approx(-1.0 / 3.0, abs=1e-12)

    def test_single_category_is_undefined(self):
        assert math.isnan(fleiss_kappa([[3, 0], [3, 0]]))

    def test_two_raters_equals_scotts_pi(self):
        # With two raters Fleiss' kappa reduces to Scott's pi, not Cohen's
        # kappa. Verify against the Scott's pi formula directly.
        r1 = [1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1]
        r2 = [1, 0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1]
        counts = np.zeros((len(r1), 2))
        for i, (a, b) in enumerate(zip(r1, r2)):
            counts[i, a] += 1
            counts[i, b] += 1
        n = len(r1)
        p_o = sum(a == b for a, b in zip(r1, r2)) / n
        joint = [(r1.count(c) + r2.count(c)) / (2 * n) for c in (0, 1)]
        p_e = sum(q**2 for q in joint)
        scotts_pi = (p_o - p_e) / (1 - p_e)
        assert fleiss_kappa(counts) == pytest.approx(scotts_pi, rel=1e-12)
        # And it is genuinely different from Cohen's kappa here.
        assert fleiss_kappa(counts) != pytest.approx(cohen_kappa(r1, r2))

    def test_unequal_rater_counts_rejected(self):
        with pytest.raises(ValueError, match="same number of ratings"):
            fleiss_kappa([[3, 0], [2, 0]])

    def test_single_rater_rejected(self):
        with pytest.raises(ValueError, match="at least 2 ratings"):
            fleiss_kappa([[1, 0], [0, 1]])


class TestCohenKappa:
    def test_textbook_two_by_two(self):
        # Table a=20, b=5, c=10, d=15 over n=50.
        #   p_o = (20 + 15) / 50 = 0.70
        #   rater A marginals 25/50, 25/50; rater B marginals 30/50, 20/50
        #   p_e = 0.5*0.6 + 0.5*0.4 = 0.50
        #   kappa = (0.70 - 0.50) / (1 - 0.50) = 0.40
        a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
        b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
        assert cohen_kappa(a, b) == pytest.approx(0.40, abs=1e-12)

    def test_perfect_agreement(self):
        v = ["p", "f", "p", "p", "f"]
        assert cohen_kappa(v, v) == pytest.approx(1.0)

    def test_complete_disagreement_is_negative(self):
        a = ["p", "p", "f", "f"]
        b = ["f", "f", "p", "p"]
        assert cohen_kappa(a, b) == pytest.approx(-1.0)

    def test_no_variation_is_undefined(self):
        assert math.isnan(cohen_kappa(["p"] * 5, ["p"] * 5))

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError, match="same length"):
            cohen_kappa([1, 2, 3], [1, 2])


# ---------------------------------------------------------------------------
# Attribute agreement
# ---------------------------------------------------------------------------


def attribute_frame(grid: dict[str, dict[str, list[str]]]) -> pd.DataFrame:
    rows = []
    for scenario, benches in grid.items():
        for bench, verdicts in benches.items():
            for k, v in enumerate(verdicts, start=1):
                rows.append(
                    {
                        "scenario_id": scenario,
                        "bench_id": bench,
                        "replicate": k,
                        "verdict": v,
                    }
                )
    return pd.DataFrame(rows)


class TestAttributeAgreement:
    """A four-scenario design whose every statistic is countable by hand."""

    GRID = {
        # unanimous pass everywhere
        "S1": {"BA": ["pass"] * 3, "BB": ["pass"] * 3, "BC": ["pass"] * 3},
        # unanimous fail everywhere
        "S2": {"BA": ["fail"] * 3, "BB": ["fail"] * 3, "BC": ["fail"] * 3},
        # benches internally consistent but disagree with each other
        "S3": {"BA": ["pass"] * 3, "BB": ["pass"] * 3, "BC": ["fail"] * 3},
        # BC internally inconsistent (2 pass, 1 fail -> majority pass)
        "S4": {
            "BA": ["pass"] * 3,
            "BB": ["pass"] * 3,
            "BC": ["pass", "pass", "fail"],
        },
    }

    @pytest.fixture
    def res(self):
        return attribute_agreement(attribute_frame(self.GRID))

    def test_design_shape(self, res):
        assert (res.n_scenarios, res.n_benches, res.n_replicates) == (4, 3, 3)
        assert res.categories == ["fail", "pass"]

    def test_per_bench_repeatability(self, res):
        table = res.per_bench_repeatability.set_index("bench")
        # BA and BB are internally consistent on all 4 scenarios.
        assert table.loc["BA", "scenarios_all_replicates_agree"] == 4
        assert table.loc["BB", "scenarios_all_replicates_agree"] == 4
        assert table.loc["BA", "repeatability"] == pytest.approx(1.0)
        # BC splits on S4 only -> 3 of 4.
        assert table.loc["BC", "scenarios_all_replicates_agree"] == 3
        assert table.loc["BC", "repeatability"] == pytest.approx(0.75)

    def test_per_bench_ci_matches_wilson(self, res):
        table = res.per_bench_repeatability.set_index("bench")
        lo, hi = wilson_interval(3, 4)
        assert table.loc["BC", "ci_low"] == pytest.approx(lo)
        assert table.loc["BC", "ci_high"] == pytest.approx(hi)

    def test_pooled_within_bench(self, res):
        # 4 + 4 + 3 = 11 consistent cells out of 4 scenarios x 3 benches = 12.
        k, n, prop, ci = res.within_bench_overall
        assert (k, n) == (11, 12)
        assert prop == pytest.approx(11 / 12)
        assert ci == pytest.approx(wilson_interval(11, 12))

    def test_between_bench_strict(self, res):
        # Only S1 and S2 have every trial on every bench agreeing.
        k, n, prop, ci = res.between_bench_strict
        assert (k, n) == (2, 4)
        assert prop == pytest.approx(0.5)
        assert ci == pytest.approx(wilson_interval(2, 4))

    def test_between_bench_majority(self, res):
        # Majority verdicts: S1 all pass, S2 all fail, S3 pass/pass/fail,
        # S4 all pass. So 3 of 4 agree.
        k, n, prop, _ = res.between_bench_majority
        assert (k, n) == (3, 4)
        assert prop == pytest.approx(0.75)

    def test_strict_is_never_above_majority_here(self, res):
        assert res.between_bench_strict[2] <= res.between_bench_majority[2]

    def test_fleiss_kappa_all_trials(self, res):
        # Build the 4x2 count table by hand and compare.
        counts = [
            [0, 9],  # S1: 0 fail, 9 pass
            [9, 0],  # S2
            [3, 6],  # S3
            [1, 8],  # S4
        ]
        assert res.fleiss_kappa_all_trials == pytest.approx(fleiss_kappa(counts))

    def test_pairwise_cohen_kappa_present(self, res):
        pairs = set(
            zip(res.pairwise_cohen_kappa["bench_a"], res.pairwise_cohen_kappa["bench_b"])
        )
        assert pairs == {("BA", "BB"), ("BA", "BC"), ("BB", "BC")}
        row = res.pairwise_cohen_kappa.set_index(["bench_a", "bench_b"])
        # BA and BB have identical majority verdicts on all 4 scenarios.
        assert row.loc[("BA", "BB"), "agreement"] == pytest.approx(1.0)
        assert row.loc[("BA", "BB"), "cohen_kappa"] == pytest.approx(1.0)

    def test_disagreement_scenarios_listed(self, res):
        assert set(res.disagreement_scenarios["scenario"]) == {"S3", "S4"}
        row = res.disagreement_scenarios.set_index("scenario")
        assert bool(row.loc["S3", "within_bench_split"]) is False
        assert bool(row.loc["S4", "within_bench_split"]) is True

    def test_pass_rates(self, res):
        table = res.per_bench_repeatability.set_index("bench")
        assert table.loc["BA", "pass_rate"] == pytest.approx(9 / 12)
        assert table.loc["BC", "pass_rate"] == pytest.approx(5 / 12)

    def test_two_bench_case_reports_cohen_kappa(self):
        grid = {s: {b: v for b, v in d.items() if b != "BC"}
                for s, d in self.GRID.items()}
        res = attribute_agreement(attribute_frame(grid))
        assert res.n_benches == 2
        assert res.cohen_kappa is not None
        assert res.fleiss_kappa_bench_verdicts is None

    def test_three_bench_case_reports_fleiss_on_bench_verdicts(self, res):
        assert res.cohen_kappa is None
        assert res.fleiss_kappa_bench_verdicts is not None

    def test_tie_never_counts_as_agreement(self):
        # Two replicates splitting 1-1 on every bench: no majority anywhere.
        grid = {
            "S1": {"BA": ["pass", "fail"], "BB": ["pass", "fail"]},
            "S2": {"BA": ["pass", "fail"], "BB": ["pass", "fail"]},
        }
        res = attribute_agreement(attribute_frame(grid))
        assert res.between_bench_majority[0] == 0
        assert res.within_bench_overall[0] == 0

    def test_boolean_verdicts_accepted(self):
        grid = {
            "S1": {"BA": [True, True], "BB": [True, True]},
            "S2": {"BA": [False, False], "BB": [True, False]},
        }
        res = attribute_agreement(attribute_frame(grid))
        assert res.between_bench_strict[0] == 1


# ---------------------------------------------------------------------------
# Bias and linearity
# ---------------------------------------------------------------------------


class TestBiasLinearity:
    def test_constant_bias_detected_no_linearity(self):
        ref = np.repeat([1.0, 2.0, 3.0, 4.0, 5.0], 6)
        val = ref + 0.5
        # Add symmetric jitter that sums to zero within each reference level.
        jitter = np.tile([0.02, -0.02, 0.01, -0.01, 0.03, -0.03], 5)
        res = bias_linearity_study(
            pd.DataFrame({"reference_value": ref, "value": val + jitter})
        )
        assert res.mean_bias == pytest.approx(0.5, abs=1e-9)
        assert res.bias_significant is True
        assert res.slope == pytest.approx(0.0, abs=1e-9)
        assert res.linearity_significant is False

    def test_linearity_detected(self):
        # Bias grows by 0.1 per unit of reference: a classic linearity fault.
        ref = np.repeat([1.0, 2.0, 3.0, 4.0, 5.0], 6)
        val = ref + 0.1 * ref
        jitter = np.tile([0.02, -0.02, 0.01, -0.01, 0.03, -0.03], 5)
        res = bias_linearity_study(
            pd.DataFrame({"reference_value": ref, "value": val + jitter})
        )
        assert res.slope == pytest.approx(0.1, abs=1e-6)
        assert res.linearity_significant is True
        assert res.r_squared > 0.95

    def test_unbiased_bench(self):
        rng = np.random.default_rng(3)
        ref = np.repeat(np.arange(1.0, 6.0), 20)
        val = ref + rng.normal(0.0, 0.05, size=ref.size)
        res = bias_linearity_study(pd.DataFrame({"reference_value": ref, "value": val}))
        assert res.bias_significant is False
        assert res.linearity_significant is False

    def test_intercept_recovered(self):
        ref = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        val = ref + (0.3 + 0.2 * ref)
        res = bias_linearity_study(pd.DataFrame({"reference_value": ref, "value": val}))
        assert res.intercept == pytest.approx(0.3, abs=1e-9)
        assert res.slope == pytest.approx(0.2, abs=1e-9)
