"""Two-tier Gage R&R: apparatus error separated from injected scenario noise.

A single-tier crossed Gage R&R (:func:`msa_ad.gage_rr.gage_rr_anova`) treats
every repeated execution of a scenario as a replicate. On an automated-driving
simulation bench that is usually wrong, because the replicates are normally
produced by varying the random seed, and the seed drives *deliberately
injected* stochasticity: traffic-agent behaviour models, sensor-noise models,
actuator latency draws. The scatter that results is aleatory variation of the
scenario. It is a property of the stochastic model, not error of the apparatus.
A naive study charges all of it to repeatability and reports an ``EV`` term -
and therefore a ``%GRR`` - that says almost nothing about the bench.

The two-tier design separates the two by replicating twice, under two different
rules:

Tier A - **fixed-seed replicates** (``TIER_FIXED_SEED``)
    Each scenario re-executed on each bench with the seed, and every other
    input, held fixed. Any variation that survives is attributable to the
    apparatus: scheduler jitter, non-deterministic floating-point reduction
    order, uninitialised state, real-time bus timing. This is the **true
    repeatability of the bench as an instrument**. On a bench that claims
    deterministic re-execution the expected Tier-A variance is exactly zero, so
    a nonzero one is not a number to be carried forward into a ratio - it is a
    finding. It is reported as an explicit **determinism audit**.

Tier B - **varied-seed replicates** (``TIER_VARIED_SEED``)
    Seed varied per replicate, everything else held fixed. Tier-B replicate
    variance contains the apparatus term *and* the injected scenario
    stochasticity. Subtracting the Tier-A estimate leaves the **aleatory
    scenario variance**.

The crossed ANOVA is run on each tier independently and the two are reported
side by side, never combined into one figure:

* Tier A characterises the **instrument** - its ``%GRR``, ``ndc`` and per-bench
  terms are the ones that answer "how much of this verdict came from the rig?";
* Tier B characterises the **stochastic model** - the same quantities computed
  over seed-driven scatter, which is what a scenario-sampling argument needs.

Reporting a single confounded ``%GRR`` in place of the pair is the specific
error this module exists to prevent.

Estimator and its limits
------------------------
``var_aleatory = var_repeatability(Tier B) - var_repeatability(Tier A)``, a
difference of two independent variance-component estimates. It is unbiased when
the apparatus term is the same in both tiers, which is the assumption the
design rests on: the tiers differ only in whether the seed moves. Being a
difference of estimates it can come out negative when the true aleatory
variance is small relative to sampling error. Negative estimates are clamped to
zero **and flagged** (``aleatory_clamped``); a silent clamp would turn "these
two tiers are indistinguishable" into "there is no scenario stochasticity",
which is a different and much stronger statement.

The one-sided F-test ``var_repeatability(B) / var_repeatability(A)`` is
reported alongside, so a clamped estimate can be read together with the
evidence for the difference being real at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Sequence

import pandas as pd
from scipy import stats

from .gage_rr import (
    GageRRResult,
    _reject_binary,
    gage_rr_anova,
)

__all__ = [
    "MissingTierError",
    "TierMismatchError",
    "TwoTierResult",
    "two_tier_gage_rr",
    "two_tier_gage_rr_from_frames",
    "TIER_FIXED_SEED",
    "TIER_VARIED_SEED",
]

#: Default label for Tier A, the fixed-seed replicates.
TIER_FIXED_SEED = "fixed_seed"

#: Default label for Tier B, the varied-seed replicates.
TIER_VARIED_SEED = "varied_seed"


class MissingTierError(ValueError):
    """Raised when one of the two tiers is absent from the data."""


class TierMismatchError(ValueError):
    """Raised when the two tiers do not describe the same study."""


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------


@dataclass
class TwoTierResult:
    """Result of a two-tier (fixed-seed / varied-seed) Gage R&R study."""

    fixed_seed: GageRRResult
    varied_seed: GageRRResult

    scenario_col: str
    bench_col: str
    value_col: str
    tier_col: str
    fixed_seed_label: Any
    varied_seed_label: Any

    var_apparatus: float
    var_varied_replicate: float
    var_aleatory: float
    var_aleatory_raw: float
    aleatory_clamped: bool
    aleatory_sd: float
    pct_aleatory_of_varied: float

    aleatory_f: float
    aleatory_p: float
    aleatory_df_varied: int
    aleatory_df_fixed: int
    aleatory_alpha: float

    determinism_audit: pd.DataFrame
    determinism_violations: pd.DataFrame
    deterministic_benches: list
    determinism_tolerance: float

    per_bench_aleatory: pd.DataFrame

    n_replicates_fixed: int
    n_replicates_varied: int

    @property
    def aleatory_significant(self) -> bool:
        """True when Tier-B replicate variance exceeds Tier-A's at ``alpha``."""
        return bool(self.aleatory_p < self.aleatory_alpha)

    @property
    def replicates_match(self) -> bool:
        """True when both tiers used the same number of replicates per cell."""
        return self.n_replicates_fixed == self.n_replicates_varied

    @property
    def pooling_matches(self) -> bool:
        """True when both tiers made the same interaction-pooling decision.

        ``pool_interaction="auto"`` decides per tier. When the decisions differ,
        one tier's repeatability term is a pooled mean square and the other's is
        the residual mean square, so the subtraction is comparing two slightly
        different quantities. Force the decision with ``"always"`` or
        ``"never"`` if that matters for the report.
        """
        return (
            self.fixed_seed.interaction_pooled
            == self.varied_seed.interaction_pooled
        )

    @property
    def any_determinism_violation(self) -> bool:
        return not self.determinism_violations.empty

    @property
    def determinism_verdict(self) -> str:
        """``"not_declared"``, ``"upheld"`` or ``"violated"``."""
        if not self.deterministic_benches:
            return "not_declared"
        return "violated" if self.any_determinism_violation else "upheld"

    @property
    def determinism_verdict_text(self) -> str:
        tol = self.determinism_tolerance
        if self.determinism_verdict == "not_declared":
            return (
                "No bench was declared deterministic, so there is no determinism "
                "claim to audit. This is not a pass: the fixed-seed variance "
                "below is the measured apparatus repeatability, and nothing here "
                "says whether it was supposed to be zero."
            )
        names = ", ".join(str(b) for b in self.deterministic_benches)
        if self.determinism_verdict == "upheld":
            how = (
                "reproduced its cell exactly"
                if tol == 0.0
                else f"reproduced its cell to within the tolerance of {tol:g}"
            )
            return (
                f"Declared deterministic: {names}. Every fixed-seed replicate "
                f"{how}, so the determinism claim is upheld on the scenarios "
                "executed. It is not established in general: this refutes "
                "determinism when it fails and is silent when it does not."
            )
        offenders = ", ".join(
            f"{row['bench']} (SD = {row['repeatability_sd']:.6g}, widest "
            f"fixed-seed spread {row['max_cell_range']:.6g} on "
            f"{row['worst_scenario']})"
            for _, row in self.determinism_violations.iterrows()
        )
        return (
            f"Declared deterministic: {names}. DETERMINISM VIOLATED by "
            f"{offenders}. Re-executing a scenario with the seed held fixed did "
            "not reproduce the result. Until that is explained, every other "
            "figure computed from this bench inherits an unmodelled source of "
            "variation, and a seed-controlled regression comparison on it is "
            "not sound."
        )

    @property
    def aleatory_verdict_text(self) -> str:
        if self.aleatory_clamped:
            return (
                "The aleatory variance estimate came out NEGATIVE "
                f"({self.var_aleatory_raw:.6g}) and has been clamped to zero. "
                "Varying the seed did not produce measurably more scatter than "
                "holding it fixed. Either the injected stochasticity is small "
                "against apparatus noise, or the seed is not reaching the "
                "stochastic models at all - the second is a defect worth ruling "
                "out before the first is believed."
            )
        return (
            f"Aleatory scenario variance = {self.var_aleatory:.6g} "
            f"(SD {self.aleatory_sd:.6g}), which is "
            f"{self.pct_aleatory_of_varied:.1f}% of the variance a single-tier "
            "study would have charged to repeatability. The remaining "
            f"{100.0 - self.pct_aleatory_of_varied:.1f}% is the apparatus."
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _repeatability_df(result: GageRRResult) -> int:
    """Degrees of freedom behind ``result.var_repeatability``.

    When the interaction is pooled into error the repeatability estimate is the
    pooled mean square, so it carries the interaction degrees of freedom too.
    Read back off the ANOVA table rather than recomputed, so the two cannot
    drift apart.
    """
    dfs = dict(zip(result.anova["source"], result.anova["df"]))
    df = int(dfs["repeatability (error)"])
    if result.interaction_pooled:
        df += int(dfs["scenario x bench"])
    return df


def _split_tiers(
    data: pd.DataFrame,
    tier_col: str,
    fixed_seed_label: Any,
    varied_seed_label: Any,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a tier-labelled frame, refusing to guess about anything."""
    if fixed_seed_label == varied_seed_label:
        raise ValueError(
            "fixed_seed_label and varied_seed_label must differ; both are "
            f"{fixed_seed_label!r}"
        )

    present = pd.unique(data[tier_col].dropna()).tolist()
    unexpected = [t for t in present if t not in (fixed_seed_label, varied_seed_label)]
    if unexpected:
        raise TierMismatchError(
            f"column {tier_col!r} contains tier label(s) "
            f"{sorted(unexpected, key=repr)} that are neither the fixed-seed "
            f"tier ({fixed_seed_label!r}) nor the varied-seed tier "
            f"({varied_seed_label!r}). Rows are not dropped silently: name the "
            "labels explicitly with fixed_seed_label / varied_seed_label, or "
            "select the two tiers you mean before calling."
        )

    fixed = data.loc[data[tier_col] == fixed_seed_label]
    varied = data.loc[data[tier_col] == varied_seed_label]

    if fixed.empty and varied.empty:
        raise MissingTierError(
            f"no rows carry either tier label in column {tier_col!r}; observed "
            f"labels: {sorted(present, key=repr)}"
        )
    if fixed.empty:
        raise MissingTierError(
            f"the fixed-seed tier ({fixed_seed_label!r}) is absent.\n"
            "\n"
            "Without fixed-seed replicates there is nothing to subtract, and\n"
            "the varied-seed repeatability term is an upper bound on the\n"
            "apparatus error rather than an estimate of it: it also contains\n"
            "every bit of deliberately injected scenario stochasticity.\n"
            "Re-execute a subset of scenarios with the seed held fixed, or run\n"
            "msa_ad.gage_rr.gage_rr_anova() on the tier you have and report the\n"
            "result as what it is - a confounded figure."
        )
    if varied.empty:
        raise MissingTierError(
            f"the varied-seed tier ({varied_seed_label!r}) is absent.\n"
            "\n"
            "The fixed-seed tier alone characterises the apparatus, which is a\n"
            "complete and useful result - run msa_ad.gage_rr.gage_rr_anova() on\n"
            "it directly. What cannot be estimated without the varied-seed tier\n"
            "is the aleatory scenario variance, because there is no second\n"
            "replicate variance to subtract from."
        )
    return fixed, varied


def _check_same_study(
    fixed: pd.DataFrame,
    varied: pd.DataFrame,
    column: str,
    what: str,
) -> None:
    """Both tiers must cover the same scenarios and the same benches."""
    a = set(fixed[column].tolist())
    b = set(varied[column].tolist())
    if a == b:
        return
    only_fixed = sorted(a - b, key=repr)
    only_varied = sorted(b - a, key=repr)
    raise TierMismatchError(
        f"the two tiers cover different {what}s, so their results are not "
        f"comparable side by side.\n"
        f"  fixed-seed tier only : {only_fixed}\n"
        f"  varied-seed tier only: {only_varied}\n"
        f"Scenario variation, %GRR and ndc are all relative to the {what} "
        "population studied, and subtracting a variance estimated over one "
        f"population from one estimated over another is not meaningful. "
        f"Restrict both tiers to the {what}s they share, and say in the report "
        "which ones were dropped."
    )


def _determinism_audit(
    fixed: pd.DataFrame,
    result: GageRRResult,
    scenario_col: str,
    bench_col: str,
    value_col: str,
    deterministic_benches: list,
    tolerance: float,
) -> pd.DataFrame:
    """Per-bench evidence on the fixed-seed re-execution claim.

    The statistic is the within-cell **range**, max minus min over the
    replicates of one (scenario, bench) cell, not a deviation from the cell
    mean. A claim of deterministic re-execution says the replicates are the
    same number, and the range of identical numbers is exactly zero - whereas
    their distance from a computed mean is not, since the mean of three equal
    floats need not round back to that float. Auditing a zero-tolerance claim
    with a statistic that has its own floating-point error would manufacture
    violations.
    """
    cells = (
        fixed.groupby([scenario_col, bench_col], observed=True)[value_col]
        .agg(lambda v: float(v.max() - v.min()))
        .rename("cell_range")
        .reset_index()
    )

    sd_by_bench = result.per_bench_repeatability.set_index("bench")[
        "repeatability_sd"
    ]
    rows = []
    for bench, group in cells.groupby(bench_col, observed=True, sort=False):
        worst = group.loc[group["cell_range"].idxmax()]
        declared = bench in deterministic_benches
        max_range = float(worst["cell_range"])
        rows.append(
            {
                "bench": bench,
                "declared_deterministic": declared,
                "repeatability_sd": float(sd_by_bench.loc[bench]),
                "max_cell_range": max_range,
                "worst_scenario": worst[scenario_col],
                "violates": bool(declared and max_range > tolerance),
            }
        )
    audit = pd.DataFrame(rows)
    return audit.sort_values("bench", key=lambda s: s.map(repr)).reset_index(
        drop=True
    )


def _per_bench_aleatory(
    fixed: GageRRResult, varied: GageRRResult
) -> pd.DataFrame:
    """Tier-B minus Tier-A replicate variance, bench by bench."""
    a = fixed.per_bench_repeatability.set_index("bench")["repeatability_sd"]
    b = varied.per_bench_repeatability.set_index("bench")["repeatability_sd"]
    rows = []
    for bench in a.index:
        var_a = float(a.loc[bench]) ** 2
        var_b = float(b.loc[bench]) ** 2
        raw = var_b - var_a
        clamped = raw < 0.0
        var = max(raw, 0.0)
        rows.append(
            {
                "bench": bench,
                "var_apparatus": var_a,
                "var_varied_replicate": var_b,
                "var_aleatory_raw": raw,
                "var_aleatory": var,
                "aleatory_sd": math.sqrt(var),
                "clamped": clamped,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Two-tier study
# --------------------------------------------------------------------------


def two_tier_gage_rr(
    data: pd.DataFrame,
    scenario_col: str = "scenario_id",
    bench_col: str = "bench_id",
    value_col: str = "value",
    *,
    tier_col: str = "tier",
    fixed_seed_label: Any = TIER_FIXED_SEED,
    varied_seed_label: Any = TIER_VARIED_SEED,
    deterministic_benches: Sequence[Any] | None = None,
    determinism_tolerance: float = 0.0,
    pool_interaction: Literal["auto", "always", "never"] = "auto",
    interaction_alpha: float = 0.25,
    aleatory_alpha: float = 0.05,
    tolerance: float | None = None,
    allow_low_cardinality: bool = False,
) -> TwoTierResult:
    """Two-tier crossed ANOVA Gage R&R for a continuous scenario metric.

    Runs :func:`msa_ad.gage_rr.gage_rr_anova` once per tier and reports the two
    analyses side by side, plus the aleatory scenario variance implied by the
    difference and a determinism audit of any bench declared deterministic.

    Parameters
    ----------
    data:
        Long-form frame with one row per execution, covering **both** tiers.
    scenario_col, bench_col, value_col:
        Column names for the "part" (scenario), the "appraiser" (bench) and the
        continuous measurement, as in ``gage_rr_anova``.
    tier_col:
        Column holding the tier label of each execution.
    fixed_seed_label, varied_seed_label:
        Values of ``tier_col`` marking Tier A (seed held fixed) and Tier B
        (seed varied per replicate). Any other label in the column is an error
        rather than something to drop quietly.
    deterministic_benches:
        Benches whose documentation claims deterministic re-execution. For each
        of them a nonzero fixed-seed deviation is reported as a violation. The
        default of ``None`` declares nothing, which produces an audit that says
        so rather than an audit that passes.
    determinism_tolerance:
        Spread between the fixed-seed replicates of one cell, in the units of
        ``value_col``, tolerated before a declared-deterministic bench is
        flagged. The default of ``0.0`` is the literal reading of the claim.
        Raise it only to absorb a known non-associative reduction in a logging
        or export path, and state the value used - it appears in the report.
    pool_interaction, interaction_alpha, tolerance, allow_low_cardinality:
        Passed through to ``gage_rr_anova`` for both tiers, so the two analyses
        are produced under identical rules.
    aleatory_alpha:
        Significance level for the one-sided F-test that Tier-B replicate
        variance exceeds Tier-A's. Default 0.05.

    Returns
    -------
    :class:`TwoTierResult`, exposing the full ``GageRRResult`` for each tier
    (``fixed_seed`` and ``varied_seed``), the derived aleatory variance with
    its clamping flag, and the determinism audit.

    Raises
    ------
    BinaryDataError
        If ``value_col`` looks like a pass/fail verdict. Checked across both
        tiers before either analysis is attempted, so the message does not
        depend on which tier happens to be read first.
    MissingTierError
        If either tier is absent. The message states what can still be
        computed without it.
    TierMismatchError
        If the tiers carry unexpected labels, or cover different scenarios or
        different benches.
    UnbalancedDesignError
        Raised by ``gage_rr_anova`` per tier. Replicate counts must be balanced
        *within* a tier; they need not match *between* tiers, and
        ``replicates_match`` records whether they did.

    Examples
    --------
    A bench that reproduces a fixed seed exactly, and whose varied-seed
    replicates come out at ``base - 1`` and ``base + 1`` (sample variance 2):

    >>> import pandas as pd
    >>> rows = []
    >>> for tier, spread in (("fixed_seed", 0.0), ("varied_seed", 1.0)):
    ...     for scenario, base in (("S1", 10.0), ("S2", 20.0)):
    ...         for bench in ("HIL-A", "HIL-B"):
    ...             for k in (-1, 1):
    ...                 rows.append({"scenario_id": scenario, "bench_id": bench,
    ...                              "tier": tier, "value": base + spread * k})
    >>> res = two_tier_gage_rr(pd.DataFrame(rows), pool_interaction="never")
    >>> res.var_apparatus, res.var_aleatory, res.aleatory_clamped
    (0.0, 2.0, False)
    """
    for col in (scenario_col, bench_col, value_col, tier_col):
        if col not in data.columns:
            raise KeyError(f"column {col!r} not found; have {list(data.columns)}")

    # Guard before splitting, so the diagnostic is about the metric rather than
    # about whichever tier was analysed first.
    if not allow_low_cardinality:
        _reject_binary(data[value_col], value_col)

    fixed, varied = _split_tiers(
        data, tier_col, fixed_seed_label, varied_seed_label
    )
    _check_same_study(fixed, varied, scenario_col, "scenario")
    _check_same_study(fixed, varied, bench_col, "bench")

    declared = list(deterministic_benches or [])
    known = set(fixed[bench_col].tolist())
    unknown = [b for b in declared if b not in known]
    if unknown:
        raise ValueError(
            f"deterministic_benches names {sorted(unknown, key=repr)}, which "
            f"do not appear in column {bench_col!r}; have "
            f"{sorted(known, key=repr)}"
        )
    if determinism_tolerance < 0.0:
        raise ValueError("determinism_tolerance must be non-negative")

    kwargs = dict(
        scenario_col=scenario_col,
        bench_col=bench_col,
        value_col=value_col,
        pool_interaction=pool_interaction,
        interaction_alpha=interaction_alpha,
        tolerance=tolerance,
        allow_low_cardinality=True,  # already checked, on the full column
    )
    res_fixed = gage_rr_anova(fixed, **kwargs)
    res_varied = gage_rr_anova(varied, **kwargs)

    var_a = res_fixed.var_repeatability
    var_b = res_varied.var_repeatability
    raw = var_b - var_a
    clamped = raw < 0.0
    var_aleatory = max(raw, 0.0)
    pct = 100.0 * var_aleatory / var_b if var_b > 0 else float("nan")

    df_b = _repeatability_df(res_varied)
    df_a = _repeatability_df(res_fixed)
    if var_a > 0:
        f_stat = var_b / var_a
        p_value = float(stats.f.sf(f_stat, df_b, df_a))
    elif var_b > 0:
        # A perfectly repeatable apparatus: any varied-seed scatter at all is
        # infinitely more than none, and the test is degenerate rather than
        # merely significant.
        f_stat, p_value = float("inf"), 0.0
    else:
        f_stat, p_value = float("nan"), float("nan")

    audit = _determinism_audit(
        fixed,
        res_fixed,
        scenario_col,
        bench_col,
        value_col,
        declared,
        determinism_tolerance,
    )

    return TwoTierResult(
        fixed_seed=res_fixed,
        varied_seed=res_varied,
        scenario_col=scenario_col,
        bench_col=bench_col,
        value_col=value_col,
        tier_col=tier_col,
        fixed_seed_label=fixed_seed_label,
        varied_seed_label=varied_seed_label,
        var_apparatus=var_a,
        var_varied_replicate=var_b,
        var_aleatory=var_aleatory,
        var_aleatory_raw=raw,
        aleatory_clamped=bool(clamped),
        aleatory_sd=math.sqrt(var_aleatory),
        pct_aleatory_of_varied=pct,
        aleatory_f=float(f_stat),
        aleatory_p=float(p_value),
        aleatory_df_varied=df_b,
        aleatory_df_fixed=df_a,
        aleatory_alpha=aleatory_alpha,
        determinism_audit=audit,
        determinism_violations=audit.loc[audit["violates"]].reset_index(drop=True),
        deterministic_benches=declared,
        determinism_tolerance=determinism_tolerance,
        per_bench_aleatory=_per_bench_aleatory(res_fixed, res_varied),
        n_replicates_fixed=res_fixed.n_replicates,
        n_replicates_varied=res_varied.n_replicates,
    )


def two_tier_gage_rr_from_frames(
    fixed_seed: pd.DataFrame,
    varied_seed: pd.DataFrame,
    scenario_col: str = "scenario_id",
    bench_col: str = "bench_id",
    value_col: str = "value",
    *,
    tier_col: str = "tier",
    **kwargs: Any,
) -> TwoTierResult:
    """Two-tier study from two separately held datasets.

    Convenience wrapper for the common case where the fixed-seed and
    varied-seed runs live in different files. The frames are labelled and
    concatenated, then handed to :func:`two_tier_gage_rr`; everything else,
    including the guards, is identical.

    ``tier_col`` must not already exist in either frame - if it does, the data
    is already tier-labelled and :func:`two_tier_gage_rr` is the right entry
    point.
    """
    for name, frame in (("fixed_seed", fixed_seed), ("varied_seed", varied_seed)):
        if tier_col in frame.columns:
            raise ValueError(
                f"the {name} frame already has a {tier_col!r} column; it is "
                "already tier-labelled, so call two_tier_gage_rr() on the "
                "combined frame instead of splitting and relabelling it"
            )
    a = fixed_seed.assign(**{tier_col: TIER_FIXED_SEED})
    b = varied_seed.assign(**{tier_col: TIER_VARIED_SEED})
    return two_tier_gage_rr(
        pd.concat([a, b], ignore_index=True),
        scenario_col=scenario_col,
        bench_col=bench_col,
        value_col=value_col,
        tier_col=tier_col,
        fixed_seed_label=TIER_FIXED_SEED,
        varied_seed_label=TIER_VARIED_SEED,
        **kwargs,
    )
