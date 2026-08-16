"""Numerical and behavioural tests for the two-tier Gage R&R.

As elsewhere in this suite, the assertions are against values known
independently of the implementation:

* a 2 x 2 x 2 two-tier design whose every variance component is worked through
  by hand in the comments, so the aleatory subtraction can be checked with a
  pencil;
* synthetic data in which the apparatus variance and the injected scenario
  variance are fixed by construction, asserting that both are recovered;
* the guards - binary input, a missing tier, mismatched tiers - and the
  clamping flag, which is the one result that must never be silent.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
import pytest

from msa_ad import datagen
from msa_ad.gage_rr import BinaryDataError, UnbalancedDesignError, gage_rr_anova
from msa_ad.report import render_two_tier_report
from msa_ad.two_tier import (
    TIER_FIXED_SEED,
    TIER_VARIED_SEED,
    MissingTierError,
    TierMismatchError,
    two_tier_gage_rr,
    two_tier_gage_rr_from_frames,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def tier_frame(fixed: np.ndarray, varied: np.ndarray, benches=None) -> pd.DataFrame:
    """Turn two (p, o, r) arrays into the long, tier-labelled form."""
    frames = []
    for label, array in ((TIER_FIXED_SEED, fixed), (TIER_VARIED_SEED, varied)):
        p, o, r = array.shape
        names = benches or [f"B{j + 1}" for j in range(o)]
        rows = [
            {
                "scenario_id": f"S{i + 1}",
                "bench_id": names[j],
                "tier": label,
                "replicate": k + 1,
                "value": float(array[i, j, k]),
            }
            for i, j, k in itertools.product(range(p), range(o), range(r))
        ]
        frames.append(pd.DataFrame(rows))
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Hand-computed two-tier design
# ---------------------------------------------------------------------------
#
# Both tiers use the same 2 scenarios x 2 benches x 2 replicates cells, and
# the same cell means (11, 15, 21, 25), so scenario and bench effects are
# identical and only the replicate scatter differs.
#
# Tier A (seed fixed), replicates at cell mean -1 and +1:
#   S1/B1: 10, 12    S1/B2: 14, 16    S2/B1: 20, 22    S2/B2: 24, 26
#   SS_scenario 200, SS_bench 32, SS_interaction 0, SS_error 4 x 2 = 8
#   MS_error = 8/4 = 2; interaction F = 0, p = 1 > 0.25 -> pooled
#   MS_pooled  = (0 + 8) / (1 + 4) = 1.6   -> var_repeatability(A) = 1.6
#
# Tier B (seed varied), replicates at cell mean -3 and +3:
#   S1/B1:  8, 14    S1/B2: 12, 18    S2/B1: 18, 24    S2/B2: 22, 28
#   SS_scenario 200, SS_bench 32, SS_interaction 0, SS_error 4 x 18 = 72
#   MS_error = 72/4 = 18; interaction F = 0, p = 1 > 0.25 -> pooled
#   MS_pooled  = (0 + 72) / (1 + 4) = 14.4 -> var_repeatability(B) = 14.4
#   var_bench  = (32  - 14.4) / (p*r = 4)  = 4.4
#   var_scen   = (200 - 14.4) / (o*r = 4)  = 46.4
#
# Aleatory scenario variance = 14.4 - 1.6 = 12.8, SD sqrt(12.8) = 3.5777...
# Share of the Tier-B replicate variance = 100 * 12.8 / 14.4 = 88.888...%
# F = 14.4 / 1.6 = 9.0 on (5, 5) degrees of freedom (1 pooled + 4 residual).

HAND_FIXED = np.array(
    [
        [[10.0, 12.0], [14.0, 16.0]],
        [[20.0, 22.0], [24.0, 26.0]],
    ]
)
HAND_VARIED = np.array(
    [
        [[8.0, 14.0], [12.0, 18.0]],
        [[18.0, 24.0], [22.0, 28.0]],
    ]
)


class TestHandComputedTwoTier:
    @pytest.fixture
    def res(self):
        return two_tier_gage_rr(tier_frame(HAND_FIXED, HAND_VARIED))

    def test_each_tier_is_a_full_gage_rr_result(self, res):
        assert res.fixed_seed.var_repeatability == pytest.approx(1.6)
        assert res.varied_seed.var_repeatability == pytest.approx(14.4)
        assert res.fixed_seed.var_bench == pytest.approx(7.6)
        assert res.varied_seed.var_bench == pytest.approx(4.4)
        assert res.fixed_seed.var_scenario == pytest.approx(49.6)
        assert res.varied_seed.var_scenario == pytest.approx(46.4)

    def test_tier_results_match_running_the_anova_directly(self, res):
        # The two-tier path must be the existing analysis applied twice, not a
        # reimplementation of it.
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        for label, tier_result in (
            (TIER_FIXED_SEED, res.fixed_seed),
            (TIER_VARIED_SEED, res.varied_seed),
        ):
            direct = gage_rr_anova(df.loc[df["tier"] == label])
            assert tier_result.grr == pytest.approx(direct.grr)
            assert tier_result.pct_grr == pytest.approx(direct.pct_grr)
            assert tier_result.ndc == direct.ndc
            pd.testing.assert_frame_equal(tier_result.anova, direct.anova)

    def test_apparatus_and_replicate_variances(self, res):
        assert res.var_apparatus == pytest.approx(1.6)
        assert res.var_varied_replicate == pytest.approx(14.4)

    def test_aleatory_variance_is_the_difference(self, res):
        assert res.var_aleatory_raw == pytest.approx(12.8)
        assert res.var_aleatory == pytest.approx(12.8)
        assert res.aleatory_clamped is False
        assert res.aleatory_sd == pytest.approx(math.sqrt(12.8), rel=1e-12)

    def test_share_of_varied_replicate_variance(self, res):
        assert res.pct_aleatory_of_varied == pytest.approx(100 * 12.8 / 14.4)

    def test_f_test_on_the_difference(self, res):
        assert res.aleatory_f == pytest.approx(9.0)
        assert (res.aleatory_df_varied, res.aleatory_df_fixed) == (5, 5)
        assert res.aleatory_significant is True

    def test_percent_grr_differs_between_tiers(self, res):
        # The whole point: a single-tier study would have reported only the
        # Tier-B figure, which is much the worse of the two.
        assert res.varied_seed.pct_grr > res.fixed_seed.pct_grr

    def test_per_bench_split_hand_computed(self, res):
        # Per-bench figures use each bench's own within-cell mean square:
        #   Tier A, bench B1: deviations +-1 over 2 scenarios x 2 replicates,
        #     SS = 4, df = p*(r-1) = 2  -> variance 2
        #   Tier B, bench B1: deviations +-3, SS = 36, df = 2 -> variance 18
        # so the per-bench aleatory estimate is 18 - 2 = 16. It differs from
        # the headline 12.8 because the headline term follows the AIAG pooling
        # rule and this one does not; with an interaction sum of squares of
        # exactly zero, pooling spreads the same SS over one more degree of
        # freedom.
        table = res.per_bench_aleatory.set_index("bench")
        for bench in ("B1", "B2"):
            assert table.loc[bench, "var_apparatus"] == pytest.approx(2.0)
            assert table.loc[bench, "var_varied_replicate"] == pytest.approx(18.0)
            assert table.loc[bench, "var_aleatory"] == pytest.approx(16.0)
            assert bool(table.loc[bench, "clamped"]) is False

    def test_replicate_and_pooling_agreement_flags(self, res):
        assert res.replicates_match is True
        assert res.pooling_matches is True


# ---------------------------------------------------------------------------
# Recovery of variances known by construction
# ---------------------------------------------------------------------------


def synthetic_two_tier(
    apparatus_sd: float,
    aleatory_sd: float,
    *,
    seed: int,
    p: int = 12,
    o: int = 3,
    r_fixed: int = 6,
    r_varied: int = 12,
    bench_bias=(-0.2, 0.0, 0.2),
) -> pd.DataFrame:
    """Two tiers whose true variance components are fixed by construction.

    Both tiers share the same cell means. Tier A scatters by ``apparatus_sd``;
    Tier B scatters by ``apparatus_sd`` and ``aleatory_sd`` combined in
    quadrature, which is what varying the seed does on top of the apparatus.
    So the recoverable aleatory variance is ``aleatory_sd ** 2`` exactly.
    """
    rng = np.random.default_rng(seed)
    scenario_level = rng.normal(0.0, 5.0, size=p)
    varied_sd = math.hypot(apparatus_sd, aleatory_sd)
    rows = []
    for i in range(p):
        for j in range(o):
            cell_mean = scenario_level[i] + bench_bias[j]
            for label, sd, r in (
                (TIER_FIXED_SEED, apparatus_sd, r_fixed),
                (TIER_VARIED_SEED, varied_sd, r_varied),
            ):
                for k in range(r):
                    rows.append(
                        {
                            "scenario_id": f"S{i:02d}",
                            "bench_id": f"B{j}",
                            "tier": label,
                            "replicate": k + 1,
                            "value": float(rng.normal(cell_mean, sd)),
                        }
                    )
    return pd.DataFrame(rows)


class TestKnownVarianceRecovery:
    """True apparatus and aleatory variances are recovered within tolerance."""

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_recovers_both_components(self, seed):
        apparatus_sd, aleatory_sd = 0.10, 0.30
        res = two_tier_gage_rr(
            synthetic_two_tier(apparatus_sd, aleatory_sd, seed=seed)
        )
        assert res.var_apparatus == pytest.approx(apparatus_sd**2, rel=0.25)
        assert res.var_aleatory == pytest.approx(aleatory_sd**2, rel=0.15)
        assert res.aleatory_clamped is False
        assert res.aleatory_significant is True

    def test_single_tier_study_would_have_overstated_the_apparatus(self):
        # The comparison the method exists to make: charging all of the
        # varied-seed scatter to repeatability inflates EV roughly threefold
        # here, because the true aleatory SD is 3x the apparatus SD.
        res = two_tier_gage_rr(synthetic_two_tier(0.10, 0.30, seed=404))
        assert res.varied_seed.ev / res.fixed_seed.ev > 2.5
        assert res.pct_aleatory_of_varied > 85.0

    @pytest.mark.parametrize("seed", [11, 22])
    def test_recovers_a_deterministic_apparatus(self, seed):
        # apparatus_sd exactly zero: Tier A carries no variance beyond the
        # rounding residue of subtracting a cell mean, so the aleatory estimate
        # is the whole Tier-B replicate variance.
        res = two_tier_gage_rr(synthetic_two_tier(0.0, 0.25, seed=seed))
        assert res.var_apparatus == pytest.approx(0.0, abs=1e-20)
        assert res.var_aleatory == pytest.approx(0.0625, rel=0.15)
        assert res.aleatory_f > 1e6
        assert res.aleatory_p == pytest.approx(0.0, abs=1e-12)
        assert res.aleatory_significant is True

    def test_exactly_zero_apparatus_variance_gives_a_degenerate_f(self):
        # When the fixed-seed tier has no variance at all the F ratio has a
        # zero denominator. Reported as infinite rather than as a nan or a
        # very large finite number that invites over-reading.
        res = two_tier_gage_rr(determinism_frame({"HIL-A": 0.0, "HIL-B": 0.0}))
        assert res.var_apparatus == 0.0
        assert math.isinf(res.aleatory_f)
        assert res.aleatory_p == 0.0
        assert res.var_aleatory == pytest.approx(res.var_varied_replicate)

    def test_both_tiers_flat_leaves_the_f_ratio_undefined(self):
        # No variation anywhere: 0/0. Reported as nan, and not as significant.
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.0})
        df["value"] = df["scenario_id"].str[1:].astype(float)
        res = two_tier_gage_rr(df)
        assert res.var_apparatus == 0.0
        assert res.var_varied_replicate == 0.0
        assert math.isnan(res.aleatory_f)
        assert math.isnan(res.aleatory_p)
        assert res.aleatory_significant is False
        assert res.aleatory_clamped is False

    def test_no_injected_stochasticity_is_not_significant(self):
        # Seed varied but nothing downstream responds to it: the two tiers are
        # the same distribution, so the difference must not come out
        # significant. Whether it clamps is a coin toss and is not asserted.
        res = two_tier_gage_rr(synthetic_two_tier(0.20, 0.0, seed=505))
        assert res.aleatory_significant is False
        assert res.var_aleatory == pytest.approx(0.0, abs=0.02)


# ---------------------------------------------------------------------------
# Negative estimates: clamped, and never silently
# ---------------------------------------------------------------------------


class TestAleatoryClamping:
    def test_negative_difference_is_clamped_and_flagged(self):
        # Tier B is *less* scattered than Tier A: deviations +-1 against +-3.
        res = two_tier_gage_rr(tier_frame(HAND_VARIED, HAND_FIXED))
        assert res.var_aleatory_raw == pytest.approx(1.6 - 14.4)
        assert res.var_aleatory == 0.0
        assert res.aleatory_sd == 0.0
        assert res.aleatory_clamped is True

    def test_clamping_is_stated_in_the_verdict_text(self):
        res = two_tier_gage_rr(tier_frame(HAND_VARIED, HAND_FIXED))
        text = res.aleatory_verdict_text
        assert "NEGATIVE" in text
        assert "clamped" in text
        # It must offer the diagnosis, not only the number.
        assert "seed is not reaching" in text

    def test_clamping_is_stated_in_the_report(self):
        text = render_two_tier_report(two_tier_gage_rr(tier_frame(HAND_VARIED, HAND_FIXED)))
        assert "CLAMPED" in text

    def test_per_bench_clamping_is_flagged_independently(self):
        res = two_tier_gage_rr(tier_frame(HAND_VARIED, HAND_FIXED))
        assert res.per_bench_aleatory["clamped"].all()
        assert (res.per_bench_aleatory["var_aleatory"] == 0.0).all()

    def test_equal_tiers_give_zero_aleatory_variance(self):
        res = two_tier_gage_rr(tier_frame(HAND_FIXED, HAND_FIXED))
        assert res.var_aleatory == pytest.approx(0.0)
        assert res.aleatory_f == pytest.approx(1.0)
        assert res.aleatory_significant is False


# ---------------------------------------------------------------------------
# Determinism audit
# ---------------------------------------------------------------------------


def determinism_frame(fixed_spread: dict[str, float]) -> pd.DataFrame:
    """Tier A in which each bench has a chosen within-cell spread."""
    benches = list(fixed_spread)
    p, r = 4, 3
    rows = []
    for i in range(p):
        for bench in benches:
            cell = 10.0 * (i + 1)
            spread = fixed_spread[bench]
            offsets = [-spread / 2.0, 0.0, spread / 2.0][:r]
            for k, off in enumerate(offsets):
                rows.append(
                    {
                        "scenario_id": f"S{i}",
                        "bench_id": bench,
                        "tier": TIER_FIXED_SEED,
                        "replicate": k + 1,
                        "value": cell + off,
                    }
                )
            for k in range(5):
                rows.append(
                    {
                        "scenario_id": f"S{i}",
                        "bench_id": bench,
                        "tier": TIER_VARIED_SEED,
                        "replicate": k + 1,
                        "value": cell + [-1.0, -0.5, 0.0, 0.5, 1.0][k],
                    }
                )
    return pd.DataFrame(rows)


class TestDeterminismAudit:
    def test_fires_on_nonzero_fixed_seed_variance(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-A", "HIL-B"])
        assert res.any_determinism_violation is True
        assert res.determinism_verdict == "violated"
        assert res.determinism_violations["bench"].tolist() == ["HIL-B"]

    def test_exact_reproduction_is_upheld(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.0})
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-A", "HIL-B"])
        assert res.any_determinism_violation is False
        assert res.determinism_verdict == "upheld"
        assert res.determinism_violations.empty

    def test_undeclared_bench_is_never_flagged(self):
        # HIL-B is noisy, but nobody claimed it was deterministic, so its
        # fixed-seed variance is an apparatus measurement rather than a
        # contradiction.
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-A"])
        assert res.any_determinism_violation is False
        assert res.determinism_verdict == "upheld"
        table = res.determinism_audit.set_index("bench")
        assert bool(table.loc["HIL-B", "declared_deterministic"]) is False
        assert table.loc["HIL-B", "max_cell_range"] == pytest.approx(0.02)

    def test_declaring_nothing_is_not_a_pass(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr(df)
        assert res.determinism_verdict == "not_declared"
        assert res.any_determinism_violation is False
        assert "not a pass" in res.determinism_verdict_text

    def test_tolerance_absorbs_a_declared_wobble(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr(
            df,
            deterministic_benches=["HIL-B"],
            determinism_tolerance=0.05,
        )
        assert res.any_determinism_violation is False
        res_tight = two_tier_gage_rr(
            df, deterministic_benches=["HIL-B"], determinism_tolerance=0.01
        )
        assert res_tight.any_determinism_violation is True

    def test_audit_reports_the_widest_spread_and_where(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        # Widen a single cell so there is an unambiguous worst offender.
        mask = (
            (df["bench_id"] == "HIL-B")
            & (df["scenario_id"] == "S2")
            & (df["tier"] == TIER_FIXED_SEED)
            & (df["replicate"] == 3)
        )
        df.loc[mask, "value"] += 0.5
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-B"])
        row = res.determinism_audit.set_index("bench").loc["HIL-B"]
        assert row["worst_scenario"] == "S2"
        assert row["max_cell_range"] == pytest.approx(0.52)

    def test_verdict_text_names_the_offender(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-A", "HIL-B"])
        text = res.determinism_verdict_text
        assert "DETERMINISM VIOLATED" in text
        assert "HIL-B" in text

    def test_unknown_declared_bench_rejected(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        with pytest.raises(ValueError, match="deterministic_benches"):
            two_tier_gage_rr(df, deterministic_benches=["HIL-Z"])

    def test_negative_tolerance_rejected(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        with pytest.raises(ValueError, match="determinism_tolerance"):
            two_tier_gage_rr(df, determinism_tolerance=-1.0)

    def test_audit_covers_every_bench(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02, "HIL-C": 0.4})
        res = two_tier_gage_rr(df, deterministic_benches=["HIL-A"])
        assert res.determinism_audit["bench"].tolist() == [
            "HIL-A",
            "HIL-B",
            "HIL-C",
        ]


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


class TestBinaryGuard:
    def _verdict_frame(self) -> pd.DataFrame:
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df["verdict"] = np.where(df["value"] >= 18.0, "pass", "fail")
        return df

    def test_binary_verdicts_rejected(self):
        with pytest.raises(BinaryDataError):
            two_tier_gage_rr(self._verdict_frame(), value_col="verdict")

    def test_message_explains_why(self):
        with pytest.raises(BinaryDataError) as exc:
            two_tier_gage_rr(self._verdict_frame(), value_col="verdict")
        msg = str(exc.value)
        assert "attribute_agreement()" in msg
        assert "nominal category" in msg

    def test_guard_runs_before_the_tiers_are_split(self):
        # A frame whose fixed-seed tier is missing *and* whose metric is
        # binary must complain about the metric: the tier split is not the
        # user's first problem, and reporting it first would send them off to
        # collect fixed-seed data for a study that cannot be run at all.
        df = self._verdict_frame()
        df = df.loc[df["tier"] == TIER_VARIED_SEED]
        with pytest.raises(BinaryDataError):
            two_tier_gage_rr(df, value_col="verdict")

    def test_escape_hatch_bypasses_it(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df["coarse"] = np.where(df["value"] >= 18.0, 9.0, 7.0)
        res = two_tier_gage_rr(df, value_col="coarse", allow_low_cardinality=True)
        assert res.fixed_seed.n_scenarios == 2


class TestTierGuards:
    def test_missing_fixed_seed_tier(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[df["tier"] == TIER_VARIED_SEED]
        with pytest.raises(MissingTierError, match="fixed-seed tier"):
            two_tier_gage_rr(df)

    def test_missing_fixed_seed_message_states_the_consequence(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[df["tier"] == TIER_VARIED_SEED]
        with pytest.raises(MissingTierError) as exc:
            two_tier_gage_rr(df)
        msg = str(exc.value)
        assert "upper bound" in msg
        assert "confounded" in msg
        assert "gage_rr_anova()" in msg

    def test_missing_varied_seed_tier(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[df["tier"] == TIER_FIXED_SEED]
        with pytest.raises(MissingTierError, match="varied-seed tier"):
            two_tier_gage_rr(df)

    def test_missing_varied_seed_message_says_what_still_works(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[df["tier"] == TIER_FIXED_SEED]
        with pytest.raises(MissingTierError) as exc:
            two_tier_gage_rr(df)
        assert "characterises the apparatus" in str(exc.value)

    def test_wrong_labels_report_what_is_actually_present(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        with pytest.raises(TierMismatchError) as exc:
            two_tier_gage_rr(df, fixed_seed_label="A", varied_seed_label="B")
        assert "'fixed_seed'" in str(exc.value)

    def test_no_recognised_tier_at_all(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df["tier"] = float("nan")
        with pytest.raises(MissingTierError, match="no rows carry"):
            two_tier_gage_rr(df)

    def test_unexpected_tier_label_is_not_dropped_silently(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df.loc[df.index[0], "tier"] = "smoke_test"
        with pytest.raises(TierMismatchError, match="smoke_test"):
            two_tier_gage_rr(df)

    def test_identical_tier_labels_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        with pytest.raises(ValueError, match="must differ"):
            two_tier_gage_rr(
                df, fixed_seed_label=TIER_FIXED_SEED, varied_seed_label=TIER_FIXED_SEED
            )

    def test_different_scenarios_between_tiers_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[~((df["tier"] == TIER_FIXED_SEED) & (df["scenario_id"] == "S2"))]
        with pytest.raises(TierMismatchError, match="different scenarios"):
            two_tier_gage_rr(df)

    def test_different_benches_between_tiers_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        df = df.loc[~((df["tier"] == TIER_VARIED_SEED) & (df["bench_id"] == "B2"))]
        with pytest.raises(TierMismatchError, match="different benchs|different bench"):
            two_tier_gage_rr(df)

    def test_missing_tier_column_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED).drop(columns=["tier"])
        with pytest.raises(KeyError, match="tier"):
            two_tier_gage_rr(df)

    def test_missing_value_column_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        with pytest.raises(KeyError, match="not_here"):
            two_tier_gage_rr(df, value_col="not_here")


class TestUnequalReplicates:
    def test_unequal_replicate_counts_between_tiers_are_allowed(self):
        # 6 fixed-seed replicates against 12 varied-seed ones: each tier is
        # balanced in itself, which is all the ANOVA needs.
        res = two_tier_gage_rr(
            synthetic_two_tier(0.10, 0.30, seed=606, r_fixed=6, r_varied=12)
        )
        assert (res.n_replicates_fixed, res.n_replicates_varied) == (6, 12)
        assert res.replicates_match is False
        assert res.var_aleatory == pytest.approx(0.09, rel=0.2)

    def test_equal_replicate_counts_set_the_flag(self):
        res = two_tier_gage_rr(
            synthetic_two_tier(0.10, 0.30, seed=606, r_fixed=8, r_varied=8)
        )
        assert res.replicates_match is True

    def test_degrees_of_freedom_track_the_replicate_counts(self):
        res = two_tier_gage_rr(
            synthetic_two_tier(0.10, 0.30, seed=707, r_fixed=4, r_varied=10)
        )
        # 12 scenarios x 3 benches; residual df = p*o*(r-1), plus the
        # interaction df when it is pooled.
        extra = (12 - 1) * (3 - 1)
        expected_fixed = 12 * 3 * (4 - 1) + (extra if res.fixed_seed.interaction_pooled else 0)
        expected_varied = 12 * 3 * (10 - 1) + (
            extra if res.varied_seed.interaction_pooled else 0
        )
        assert res.aleatory_df_fixed == expected_fixed
        assert res.aleatory_df_varied == expected_varied

    def test_unbalanced_within_a_tier_still_rejected(self):
        df = synthetic_two_tier(0.10, 0.30, seed=808, r_fixed=4, r_varied=4)
        df = df.drop(df.index[0])
        with pytest.raises(UnbalancedDesignError):
            two_tier_gage_rr(df)


# ---------------------------------------------------------------------------
# The two-dataset entry point
# ---------------------------------------------------------------------------


class TestFromFrames:
    def test_matches_the_labelled_path(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        combined = two_tier_gage_rr(df)
        split = two_tier_gage_rr_from_frames(
            df.loc[df["tier"] == TIER_FIXED_SEED].drop(columns=["tier"]),
            df.loc[df["tier"] == TIER_VARIED_SEED].drop(columns=["tier"]),
        )
        assert split.var_apparatus == pytest.approx(combined.var_apparatus)
        assert split.var_aleatory == pytest.approx(combined.var_aleatory)
        assert split.varied_seed.pct_grr == pytest.approx(combined.varied_seed.pct_grr)

    def test_keyword_arguments_are_forwarded(self):
        df = determinism_frame({"HIL-A": 0.0, "HIL-B": 0.02})
        res = two_tier_gage_rr_from_frames(
            df.loc[df["tier"] == TIER_FIXED_SEED].drop(columns=["tier"]),
            df.loc[df["tier"] == TIER_VARIED_SEED].drop(columns=["tier"]),
            deterministic_benches=["HIL-B"],
        )
        assert res.any_determinism_violation is True

    def test_already_labelled_frame_rejected(self):
        df = tier_frame(HAND_FIXED, HAND_VARIED)
        with pytest.raises(ValueError, match="already tier-labelled"):
            two_tier_gage_rr_from_frames(
                df.loc[df["tier"] == TIER_FIXED_SEED],
                df.loc[df["tier"] == TIER_VARIED_SEED],
            )


# ---------------------------------------------------------------------------
# The bundled example must contain findings
# ---------------------------------------------------------------------------


class TestExampleDataContainsFindings:
    @pytest.fixture
    def res(self):
        return two_tier_gage_rr(
            datagen.generate_two_tier_runs(),
            value_col="min_ttc_s",
            deterministic_benches=datagen.DETERMINISTIC_BENCHES,
        )

    def test_two_tier_data_is_deterministic(self):
        pd.testing.assert_frame_equal(
            datagen.generate_two_tier_runs(),
            datagen.generate_two_tier_runs(),
        )

    def test_determinism_audit_fires_on_one_bench(self, res):
        assert res.any_determinism_violation is True
        assert res.determinism_violations["bench"].tolist() == ["HIL-B"]

    def test_the_honest_deterministic_bench_passes(self, res):
        table = res.determinism_audit.set_index("bench")
        assert table.loc["HIL-A", "max_cell_range"] == 0.0
        assert bool(table.loc["HIL-A", "violates"]) is False

    def test_injected_stochasticity_dominates_the_replicate_variance(self, res):
        assert res.pct_aleatory_of_varied > 80.0
        assert res.aleatory_significant is True

    def test_aleatory_sd_recovers_the_constructed_value(self, res):
        assert res.aleatory_sd == pytest.approx(
            datagen.SCENARIO_ALEATORY_SD_S, rel=0.15
        )

    def test_the_single_tier_figure_would_have_been_worse(self, res):
        # A one-tier study on the varied-seed data alone reports the bench as
        # unacceptable; the instrument itself is not that bad.
        assert res.varied_seed.pct_grr > res.fixed_seed.pct_grr
        assert res.fixed_seed.ndc > res.varied_seed.ndc

    def test_generate_all_includes_the_two_tier_table(self):
        tables = datagen.generate_all()
        assert "bench_runs_two_tier" in tables
        assert set(tables["bench_runs_two_tier"]["tier"]) == {
            TIER_FIXED_SEED,
            TIER_VARIED_SEED,
        }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestReportRenders:
    def _check(self, text: str) -> None:
        assert text.strip()
        over = [ln for ln in text.splitlines() if len(ln) > 100]
        assert not over, f"lines exceed 100 chars: {over[:2]}"

    def test_example_report(self):
        res = two_tier_gage_rr(
            datagen.generate_two_tier_runs(),
            value_col="min_ttc_s",
            deterministic_benches=datagen.DETERMINISTIC_BENCHES,
        )
        text = render_two_tier_report(res)
        self._check(text)
        assert "DETERMINISM AUDIT" in text
        assert "ALEATORY SCENARIO VARIANCE" in text
        assert "VIOLATED" in text
        # Both tiers must appear; the point is that they are not merged.
        assert "Tier A (fixed seed)" in text
        assert "Tier B (varied seed)" in text

    def test_report_without_a_determinism_claim(self):
        text = render_two_tier_report(two_tier_gage_rr(tier_frame(HAND_FIXED, HAND_VARIED)))
        self._check(text)
        assert "No bench was declared deterministic" in text

    def test_report_notes_unequal_replicate_counts(self):
        res = two_tier_gage_rr(
            synthetic_two_tier(0.10, 0.30, seed=909, r_fixed=4, r_varied=9)
        )
        text = render_two_tier_report(res)
        self._check(text)
        assert "different replicate counts" in text

    def test_single_tier_reports_still_render_for_each_tier(self):
        from msa_ad.report import render_gage_rr_report

        res = two_tier_gage_rr(tier_frame(HAND_FIXED, HAND_VARIED))
        for tier in (res.fixed_seed, res.varied_seed):
            self._check(render_gage_rr_report(tier))
