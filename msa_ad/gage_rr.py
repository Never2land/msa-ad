"""Gage R&R and attribute agreement analysis for automated-driving test benches.

Two distinct analyses live here, and they must not be confused:

``gage_rr_anova``
    Crossed ANOVA Gage R&R for *continuous* safety-margin metrics (minimum
    time-to-collision, minimum clearance, maximum lateral deviation, ...).
    Follows the ANOVA method of AIAG MSA 4th edition. In the automotive
    production vocabulary the "part" is the **scenario**, the "appraiser" is
    the **bench**, and the trials/replicates are repeated executions of the
    same scenario on the same bench (typically varying the random seed).

``attribute_agreement``
    Agreement analysis for *binary* pass/fail scenario verdicts. A verdict is
    a nominal category, not a measurement on an interval scale, so variance
    decomposition is not meaningful. Repeatability and reproducibility are
    reported as agreement proportions with Wilson score confidence intervals,
    plus chance-corrected agreement (Fleiss' / Cohen's kappa).

Passing binary data to ``gage_rr_anova`` raises :class:`BinaryDataError`.

Terminology note on AV
----------------------
AIAG defines reproducibility as the variation between appraisers, and in the
ANOVA method the appraiser-by-part interaction is part of the reproducibility
term. This module therefore reports:

* ``ev``            = sqrt(var_repeatability)
* ``av``            = sqrt(var_appraiser + var_interaction)   (reproducibility)
* ``av_bench_only`` = sqrt(var_appraiser)                     (pure bench term)
* ``interaction``   = sqrt(var_interaction)
* ``grr``           = sqrt(ev**2 + av**2)

The appraiser variance component is ``(MS_appraiser - MS_interaction) / (p*r)``
when the interaction is retained, so the pure bench term is not inflated by
interaction or residual variance. When the interaction is pooled into error
(the AIAG rule below) ``interaction`` is zero by construction and ``av``
reduces to the pure bench term, so ``grr == sqrt(ev**2 + av**2)`` in the usual
AIAG-table sense either way.

Pooling rule
------------
AIAG MSA tests the appraiser-by-part interaction at alpha = 0.25. If the
interaction is not significant at that level it is pooled into the error term
and the variance components are recomputed from the pooled residual. This is
implemented as ``pool_interaction="auto"`` (the default); ``"always"`` and
``"never"`` force the decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal, Sequence

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "BinaryDataError",
    "UnbalancedDesignError",
    "GageRRResult",
    "AttributeAgreementResult",
    "BiasLinearityResult",
    "gage_rr_anova",
    "attribute_agreement",
    "bias_linearity_study",
    "wilson_interval",
    "fleiss_kappa",
    "cohen_kappa",
    "looks_binary",
]

Z_FOR_95 = 1.959963984540054

# AIAG MSA acceptance thresholds on %GRR (percent of total variation).
GRR_ACCEPTABLE_PCT = 10.0
GRR_MARGINAL_PCT = 30.0
NDC_MINIMUM = 5


class BinaryDataError(ValueError):
    """Raised when binary pass/fail data is passed to the continuous ANOVA path."""


class UnbalancedDesignError(ValueError):
    """Raised when the crossed design is not balanced / has empty cells."""


# --------------------------------------------------------------------------
# Interval estimation
# --------------------------------------------------------------------------


def wilson_interval(
    successes: int, n: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    The Wilson interval is used throughout this package instead of the normal
    (Wald) approximation. Seeded-fault campaigns and bench studies produce
    small samples, and the Wald interval degenerates near p = 0 and p = 1
    (it can even produce bounds outside [0, 1] or a zero-width interval).

    Parameters
    ----------
    successes, n:
        Number of successes and number of trials. ``0 <= successes <= n``.
    confidence:
        Two-sided confidence level, default 0.95.

    Returns
    -------
    (low, high), clipped to [0, 1]. ``(nan, nan)`` when ``n == 0``.

    Examples
    --------
    >>> lo, hi = wilson_interval(0, 10)
    >>> round(lo, 4), round(hi, 4)
    (0.0, 0.2775)
    >>> lo, hi = wilson_interval(15, 20)
    >>> round(lo, 4), round(hi, 4)
    (0.5313, 0.8881)
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if not 0 <= successes <= n:
        raise ValueError(f"successes ({successes}) must be in [0, n] (n={n})")
    if n == 0:
        return (float("nan"), float("nan"))
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")

    z = stats.norm.ppf(0.5 + confidence / 2.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# --------------------------------------------------------------------------
# Chance-corrected agreement
# --------------------------------------------------------------------------


def fleiss_kappa(counts: np.ndarray | Sequence[Sequence[int]]) -> float:
    """Fleiss' kappa for a fixed number of raters per subject.

    Parameters
    ----------
    counts:
        ``(N, k)`` integer array. ``counts[i, j]`` is the number of raters who
        assigned subject ``i`` to category ``j``. Every row must sum to the
        same value ``n`` (the number of raters), and ``n >= 2``.

    Notes
    -----
    With exactly two raters Fleiss' kappa equals **Scott's pi**, not Cohen's
    kappa: Fleiss' kappa pools the raters into a single marginal distribution
    rather than allowing each rater its own marginal. For the two-bench case
    use :func:`cohen_kappa` as well; the two statistics answer slightly
    different questions and generally differ.
    """
    m = np.asarray(counts, dtype=float)
    if m.ndim != 2:
        raise ValueError("counts must be a 2-D (subjects x categories) array")
    if np.any(m < 0):
        raise ValueError("counts must be non-negative")

    row_totals = m.sum(axis=1)
    n = row_totals[0]
    if not np.allclose(row_totals, n):
        raise ValueError(
            "Fleiss' kappa requires the same number of ratings for every "
            f"subject; got row sums ranging {row_totals.min()}..{row_totals.max()}"
        )
    if n < 2:
        raise ValueError("Fleiss' kappa requires at least 2 ratings per subject")

    N = m.shape[0]
    # Per-subject observed agreement.
    p_i = (np.square(m).sum(axis=1) - n) / (n * (n - 1.0))
    p_bar = p_i.mean()
    # Marginal category proportions.
    p_j = m.sum(axis=0) / (N * n)
    p_e = np.square(p_j).sum()

    if math.isclose(p_e, 1.0):
        # All raters used a single category: agreement is perfect but kappa
        # is undefined (0/0). Report nan rather than a misleading 1.0.
        return float("nan")
    return float((p_bar - p_e) / (1.0 - p_e))


def cohen_kappa(rater_a: Sequence[Any], rater_b: Sequence[Any]) -> float:
    """Cohen's kappa for two raters over paired nominal ratings.

    Examples
    --------
    A 2x2 table with a=20, b=5, c=10, d=15 gives kappa = 0.4.
    """
    a = np.asarray(list(rater_a))
    b = np.asarray(list(rater_b))
    if a.shape != b.shape:
        raise ValueError("rater_a and rater_b must have the same length")
    n = a.size
    if n == 0:
        raise ValueError("no ratings supplied")

    categories = sorted(set(a.tolist()) | set(b.tolist()), key=repr)
    idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    table = np.zeros((k, k), dtype=float)
    for x, y in zip(a.tolist(), b.tolist()):
        table[idx[x], idx[y]] += 1.0

    p_o = np.trace(table) / n
    p_e = float((table.sum(axis=1) / n) @ (table.sum(axis=0) / n))
    if math.isclose(p_e, 1.0):
        return float("nan")
    return float((p_o - p_e) / (1.0 - p_e))


# --------------------------------------------------------------------------
# Binary-data guard
# --------------------------------------------------------------------------


def looks_binary(values: Sequence[Any] | np.ndarray | pd.Series) -> bool:
    """True when ``values`` looks like a two-level pass/fail verdict.

    Detects boolean dtype, {0, 1} coding, string verdicts such as
    ``pass``/``fail``, and any column with two or fewer distinct values.
    """
    s = pd.Series(list(values) if not isinstance(values, pd.Series) else values)
    s = s.dropna()
    if s.empty:
        return False
    if s.dtype == bool or isinstance(s.dtype, pd.CategoricalDtype):
        return True
    if not pd.api.types.is_numeric_dtype(s):
        return True  # non-numeric verdicts are categorical by definition
    unique = pd.unique(s)
    if unique.size <= 2:
        return True
    return False


def _reject_binary(values: pd.Series, column: str) -> None:
    if not looks_binary(values):
        return
    observed = sorted(pd.unique(values.dropna()).tolist(), key=repr)[:4]
    raise BinaryDataError(
        f"Column {column!r} looks like a binary / categorical pass-fail\n"
        f"verdict (distinct values observed: {observed}).\n"
        "\n"
        "Crossed ANOVA Gage R&R decomposes the variance of a measurement on\n"
        "a continuous scale into repeatability, reproducibility and part\n"
        "variation. A pass/fail verdict is a nominal category, so:\n"
        "  - its 'variance' has no physical units and the components are not\n"
        "    interpretable as measurement error;\n"
        "  - %GRR cannot be compared against the AIAG 10% / 30% thresholds;\n"
        "  - ndc, which counts resolvable levels of a continuous scale, is\n"
        "    meaningless for two categories.\n"
        "For a Bernoulli variable the variance is a deterministic function of\n"
        "the mean, p*(1-p). A bench that simply fails more scenarios would\n"
        "therefore appear to have different 'repeatability' purely because\n"
        "its pass rate differs, which is not a property of the apparatus.\n"
        "\n"
        "Use msa_ad.gage_rr.attribute_agreement() instead. It reports\n"
        "within-bench repeatability, between-bench reproducibility, and\n"
        "Fleiss' / Cohen's kappa, all with Wilson score confidence intervals.\n"
        "\n"
        "If this column really is a continuous safety-margin metric that\n"
        "happens to take few distinct values in this sample, supply more\n"
        "resolution (e.g. minimum TTC in seconds rather than a rounded flag)\n"
        "or pass allow_low_cardinality=True."
    )


# --------------------------------------------------------------------------
# Crossed ANOVA Gage R&R
# --------------------------------------------------------------------------


@dataclass
class GageRRResult:
    """Result of a crossed ANOVA Gage R&R study."""

    n_scenarios: int
    n_benches: int
    n_replicates: int
    scenario_col: str
    bench_col: str
    value_col: str

    anova: pd.DataFrame
    interaction_f: float
    interaction_p: float
    interaction_pooled: bool
    interaction_alpha: float

    var_repeatability: float
    var_bench: float
    var_interaction: float
    var_scenario: float

    ev: float
    av: float
    av_bench_only: float
    interaction: float
    grr: float
    pv: float
    tv: float

    pct_ev: float
    pct_av: float
    pct_interaction: float
    pct_grr: float
    pct_pv: float

    ndc: int
    tolerance: float | None = None
    pct_grr_tolerance: float | None = None

    bench_means: pd.Series = field(default_factory=pd.Series)
    per_bench_repeatability: pd.DataFrame = field(default_factory=pd.DataFrame)
    levene_stat: float | None = None
    levene_p: float | None = None

    @property
    def verdict(self) -> str:
        """AIAG acceptance category for %GRR."""
        if self.pct_grr < GRR_ACCEPTABLE_PCT:
            return "acceptable"
        if self.pct_grr <= GRR_MARGINAL_PCT:
            return "marginal"
        return "unacceptable"

    @property
    def verdict_text(self) -> str:
        return {
            "acceptable": (
                f"%GRR = {self.pct_grr:.1f}% < {GRR_ACCEPTABLE_PCT:.0f}% - "
                "measurement system acceptable (AIAG MSA)."
            ),
            "marginal": (
                f"%GRR = {self.pct_grr:.1f}% is between {GRR_ACCEPTABLE_PCT:.0f}% "
                f"and {GRR_MARGINAL_PCT:.0f}% - conditionally acceptable (AIAG "
                "MSA); acceptance depends on application importance, cost of "
                "the measurement device and cost of repair."
            ),
            "unacceptable": (
                f"%GRR = {self.pct_grr:.1f}% > {GRR_MARGINAL_PCT:.0f}% - "
                "measurement system unacceptable (AIAG MSA); it needs "
                "improvement before its verdicts can be relied upon."
            ),
        }[self.verdict]

    @property
    def ndc_ok(self) -> bool:
        return self.ndc >= NDC_MINIMUM


def _to_balanced_array(
    df: pd.DataFrame,
    scenario_col: str,
    bench_col: str,
    value_col: str,
) -> tuple[np.ndarray, list, list]:
    """Reshape long-form data into a (p, o, r) array, validating balance."""
    scenarios = sorted(pd.unique(df[scenario_col]).tolist(), key=repr)
    benches = sorted(pd.unique(df[bench_col]).tolist(), key=repr)
    p, o = len(scenarios), len(benches)

    if p < 2:
        raise UnbalancedDesignError(
            f"need at least 2 distinct {scenario_col!r} values, got {p}"
        )
    if o < 2:
        raise UnbalancedDesignError(
            f"need at least 2 distinct {bench_col!r} values, got {o}. "
            "With a single bench there is no reproducibility to estimate; "
            "run a repeatability-only study instead."
        )

    sizes = df.groupby([scenario_col, bench_col], observed=True).size()
    if len(sizes) != p * o:
        missing = p * o - len(sizes)
        raise UnbalancedDesignError(
            f"crossed design has {missing} empty cell(s): every scenario must "
            "be run on every bench. The ANOVA method implemented here assumes "
            "a balanced crossed design."
        )
    r = int(sizes.iloc[0])
    if sizes.nunique() != 1:
        raise UnbalancedDesignError(
            "unbalanced design: replicate counts per (scenario, bench) cell "
            f"range {sizes.min()}..{sizes.max()}. Balance the study or drop "
            "cells down to a common replicate count."
        )
    if r < 2:
        raise UnbalancedDesignError(
            "need at least 2 replicates per (scenario, bench) cell to separate "
            f"repeatability from the other terms, got {r}."
        )

    s_idx = {s: i for i, s in enumerate(scenarios)}
    b_idx = {b: j for j, b in enumerate(benches)}
    arr = np.full((p, o, r), np.nan)
    fill = np.zeros((p, o), dtype=int)
    for s, b, v in zip(df[scenario_col], df[bench_col], df[value_col]):
        i, j = s_idx[s], b_idx[b]
        arr[i, j, fill[i, j]] = v
        fill[i, j] += 1
    if np.isnan(arr).any():
        raise UnbalancedDesignError("missing values in the measurement column")
    return arr, scenarios, benches


def gage_rr_anova(
    data: pd.DataFrame,
    scenario_col: str = "scenario_id",
    bench_col: str = "bench_id",
    value_col: str = "value",
    *,
    pool_interaction: Literal["auto", "always", "never"] = "auto",
    interaction_alpha: float = 0.25,
    tolerance: float | None = None,
    allow_low_cardinality: bool = False,
) -> GageRRResult:
    """Crossed ANOVA Gage R&R for a continuous scenario metric.

    Parameters
    ----------
    data:
        Long-form frame with one row per execution.
    scenario_col, bench_col, value_col:
        Column names for the "part" (scenario), the "appraiser" (bench) and
        the continuous measurement.
    pool_interaction:
        ``"auto"`` applies the AIAG rule: pool the scenario-by-bench
        interaction into error when its F-test p-value exceeds
        ``interaction_alpha``. ``"always"`` / ``"never"`` force the decision.
    interaction_alpha:
        Significance level for the interaction test. AIAG MSA uses 0.25.
    tolerance:
        Optional total tolerance (upper spec minus lower spec) for the metric.
        When given, ``pct_grr_tolerance = 100 * 6 * GRR / tolerance`` is also
        reported (the study variation multiplier 6 is the AIAG default).
    allow_low_cardinality:
        Bypass the binary-data guard. Only set this when the metric really is
        continuous but happens to show few distinct values.

    Raises
    ------
    BinaryDataError
        If ``value_col`` looks like a pass/fail verdict.
    UnbalancedDesignError
        If the crossed design is unbalanced, has empty cells, or has fewer
        than 2 replicates / 2 benches / 2 scenarios.
    """
    for col in (scenario_col, bench_col, value_col):
        if col not in data.columns:
            raise KeyError(f"column {col!r} not found; have {list(data.columns)}")

    values = data[value_col]
    if not allow_low_cardinality:
        _reject_binary(values, value_col)
    if not pd.api.types.is_numeric_dtype(values):
        raise TypeError(
            f"column {value_col!r} is not numeric (dtype={values.dtype}); "
            "the ANOVA method needs a measurement on a continuous scale"
        )

    x, scenarios, benches = _to_balanced_array(
        data, scenario_col, bench_col, value_col
    )
    p, o, r = x.shape

    grand = x.mean()
    scenario_means = x.mean(axis=(1, 2))
    bench_means = x.mean(axis=(0, 2))
    cell_means = x.mean(axis=2)

    ss_scenario = o * r * float(np.sum((scenario_means - grand) ** 2))
    ss_bench = p * r * float(np.sum((bench_means - grand) ** 2))
    resid = cell_means - scenario_means[:, None] - bench_means[None, :] + grand
    ss_interaction = r * float(np.sum(resid**2))
    ss_error = float(np.sum((x - cell_means[:, :, None]) ** 2))
    ss_total = float(np.sum((x - grand) ** 2))

    df_scenario = p - 1
    df_bench = o - 1
    df_interaction = (p - 1) * (o - 1)
    df_error = p * o * (r - 1)

    ms_scenario = ss_scenario / df_scenario
    ms_bench = ss_bench / df_bench
    ms_interaction = ss_interaction / df_interaction
    ms_error = ss_error / df_error

    f_interaction = ms_interaction / ms_error if ms_error > 0 else float("inf")
    p_interaction = float(stats.f.sf(f_interaction, df_interaction, df_error))

    if pool_interaction == "auto":
        pooled = p_interaction > interaction_alpha
    elif pool_interaction == "always":
        pooled = True
    elif pool_interaction == "never":
        pooled = False
    else:
        raise ValueError("pool_interaction must be 'auto', 'always' or 'never'")

    if pooled:
        df_pooled = df_interaction + df_error
        ms_pooled = (ss_interaction + ss_error) / df_pooled
        var_repeat = ms_pooled
        var_interaction = 0.0
        var_bench = max((ms_bench - ms_pooled) / (p * r), 0.0)
        var_scenario = max((ms_scenario - ms_pooled) / (o * r), 0.0)
    else:
        var_repeat = ms_error
        var_interaction = max((ms_interaction - ms_error) / r, 0.0)
        var_bench = max((ms_bench - ms_interaction) / (p * r), 0.0)
        var_scenario = max((ms_scenario - ms_interaction) / (o * r), 0.0)

    ev = math.sqrt(var_repeat)
    av_bench_only = math.sqrt(var_bench)
    interaction_sd = math.sqrt(var_interaction)
    # AIAG reproducibility: bench effect plus scenario-by-bench interaction.
    av = math.sqrt(var_bench + var_interaction)
    grr = math.sqrt(var_repeat + var_bench + var_interaction)
    pv = math.sqrt(var_scenario)
    tv = math.sqrt(grr**2 + pv**2)

    def pct(v: float) -> float:
        return 100.0 * v / tv if tv > 0 else float("nan")

    ndc = int(math.floor(1.41 * pv / grr)) if grr > 0 else 0

    anova = pd.DataFrame(
        {
            "source": [
                f"{scenario_col} (scenario)",
                f"{bench_col} (bench)",
                "scenario x bench",
                "repeatability (error)",
                "total",
            ],
            "df": [
                df_scenario,
                df_bench,
                df_interaction,
                df_error,
                p * o * r - 1,
            ],
            "ss": [ss_scenario, ss_bench, ss_interaction, ss_error, ss_total],
            "ms": [ms_scenario, ms_bench, ms_interaction, ms_error, np.nan],
            "f": [
                ms_scenario / ms_interaction if ms_interaction > 0 else np.nan,
                ms_bench / ms_interaction if ms_interaction > 0 else np.nan,
                f_interaction,
                np.nan,
                np.nan,
            ],
            "p_value": [np.nan, np.nan, p_interaction, np.nan, np.nan],
        }
    )

    # Per-bench repeatability: pooled within-cell standard deviation for each
    # bench. This is what identifies a single misbehaving bench, which the
    # aggregate EV term averages away.
    rows = []
    resid_by_bench = []
    for j, bench in enumerate(benches):
        dev = (x[:, j, :] - cell_means[:, j][:, None]).ravel()
        resid_by_bench.append(dev)
        ss_j = float(np.sum(dev**2))
        df_j = p * (r - 1)
        rows.append(
            {
                "bench": bench,
                "mean": float(bench_means[j]),
                "bias_vs_grand_mean": float(bench_means[j] - grand),
                "repeatability_sd": math.sqrt(ss_j / df_j),
                "df": df_j,
            }
        )
    per_bench = pd.DataFrame(rows)
    ratio = per_bench["repeatability_sd"] / per_bench["repeatability_sd"].min()
    per_bench["sd_ratio_vs_best"] = ratio

    # Levene test for equal within-bench variance. It is undefined when the
    # absolute deviations have no within-group spread at all (for example a
    # 2-replicate design in which every cell happens to have the same range):
    # the statistic is then 0/0. Detect that case up front rather than
    # emitting a nan and a runtime warning.
    levene_stat = levene_p = None
    if o >= 2:
        z_groups = [np.abs(d - d.mean()) for d in resid_by_bench]
        within_ss = sum(float(np.sum((z - z.mean()) ** 2)) for z in z_groups)
        if within_ss > 0:
            lev = stats.levene(*resid_by_bench, center="mean")
            levene_stat, levene_p = float(lev.statistic), float(lev.pvalue)

    pct_grr_tol = None
    if tolerance is not None:
        if tolerance <= 0:
            raise ValueError("tolerance must be positive")
        pct_grr_tol = 100.0 * 6.0 * grr / tolerance

    return GageRRResult(
        n_scenarios=p,
        n_benches=o,
        n_replicates=r,
        scenario_col=scenario_col,
        bench_col=bench_col,
        value_col=value_col,
        anova=anova,
        interaction_f=float(f_interaction),
        interaction_p=p_interaction,
        interaction_pooled=bool(pooled),
        interaction_alpha=interaction_alpha,
        var_repeatability=var_repeat,
        var_bench=var_bench,
        var_interaction=var_interaction,
        var_scenario=var_scenario,
        ev=ev,
        av=av,
        av_bench_only=av_bench_only,
        interaction=interaction_sd,
        grr=grr,
        pv=pv,
        tv=tv,
        pct_ev=pct(ev),
        pct_av=pct(av),
        pct_interaction=pct(interaction_sd),
        pct_grr=pct(grr),
        pct_pv=pct(pv),
        ndc=ndc,
        tolerance=tolerance,
        pct_grr_tolerance=pct_grr_tol,
        bench_means=pd.Series(bench_means, index=benches, name="mean"),
        per_bench_repeatability=per_bench,
        levene_stat=levene_stat,
        levene_p=levene_p,
    )


# --------------------------------------------------------------------------
# Attribute agreement (binary verdicts)
# --------------------------------------------------------------------------


@dataclass
class AttributeAgreementResult:
    """Result of an attribute (pass/fail verdict) agreement study."""

    n_scenarios: int
    n_benches: int
    n_replicates: int
    scenario_col: str
    bench_col: str
    verdict_col: str
    categories: list

    per_bench_repeatability: pd.DataFrame
    within_bench_overall: tuple[int, int, float, tuple[float, float]]
    between_bench_strict: tuple[int, int, float, tuple[float, float]]
    between_bench_majority: tuple[int, int, float, tuple[float, float]]

    fleiss_kappa_all_trials: float
    fleiss_kappa_bench_verdicts: float | None
    cohen_kappa: float | None
    pairwise_cohen_kappa: pd.DataFrame

    bench_pass_rate: pd.DataFrame
    disagreement_scenarios: pd.DataFrame
    confidence: float = 0.95


def _kappa_label(k: float) -> str:
    """Landis & Koch (1977) descriptive bands for kappa."""
    if math.isnan(k):
        return "undefined (no variation in verdicts)"
    if k < 0.0:
        return "worse than chance"
    if k < 0.20:
        return "slight"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial"
    return "almost perfect"


def attribute_agreement(
    data: pd.DataFrame,
    scenario_col: str = "scenario_id",
    bench_col: str = "bench_id",
    verdict_col: str = "verdict",
    *,
    confidence: float = 0.95,
) -> AttributeAgreementResult:
    """Attribute agreement analysis for binary pass/fail scenario verdicts.

    Reports, each with a Wilson score interval:

    * per-bench repeatability - the proportion of scenarios for which all
      replicates on that bench produced the same verdict;
    * overall within-bench repeatability - pooled over all (scenario, bench)
      cells;
    * between-bench reproducibility, strict - the proportion of scenarios for
      which *every* observation on *every* bench agreed (the AIAG "all
      appraisers agree" statistic; it is deliberately conservative because it
      also fails when a single bench is internally inconsistent);
    * between-bench reproducibility, majority - each bench first reduced to
      its majority verdict, then agreement measured across benches. This
      isolates reproducibility from repeatability. Ties (an even number of
      replicates splitting evenly) are treated as their own state, so a bench
      that cannot make up its mind never counts as agreeing.

    Plus Fleiss' kappa over all trials, Fleiss' kappa over bench majority
    verdicts (3+ benches), and pairwise Cohen's kappa on majority verdicts.
    """
    for col in (scenario_col, bench_col, verdict_col):
        if col not in data.columns:
            raise KeyError(f"column {col!r} not found; have {list(data.columns)}")

    verdicts = data[verdict_col]
    categories = sorted(pd.unique(verdicts.dropna()).tolist(), key=repr)
    if len(categories) > 2:
        raise ValueError(
            f"attribute_agreement expects a binary verdict; column "
            f"{verdict_col!r} has {len(categories)} distinct values: "
            f"{categories}"
        )

    scenarios = sorted(pd.unique(data[scenario_col]).tolist(), key=repr)
    benches = sorted(pd.unique(data[bench_col]).tolist(), key=repr)
    p, o = len(scenarios), len(benches)
    if o < 2:
        raise UnbalancedDesignError(
            "need at least 2 benches for a reproducibility analysis"
        )

    sizes = data.groupby([scenario_col, bench_col], observed=True).size()
    if len(sizes) != p * o or sizes.nunique() != 1:
        raise UnbalancedDesignError(
            "attribute agreement requires a balanced crossed design: every "
            "scenario run the same number of times on every bench"
        )
    r = int(sizes.iloc[0])

    grid: dict[tuple[Any, Any], list] = {
        (s, b): [] for s in scenarios for b in benches
    }
    for s, b, v in zip(data[scenario_col], data[bench_col], verdicts):
        grid[(s, b)].append(v)

    def _majority(vals: list) -> Any:
        counts = {c: vals.count(c) for c in set(vals)}
        best = max(counts.values())
        winners = [c for c, n in counts.items() if n == best]
        if len(winners) == 1:
            return winners[0]
        return "__TIE__"

    # Per-bench repeatability.
    rows = []
    within_agree = 0
    for b in benches:
        agree = sum(len(set(grid[(s, b)])) == 1 for s in scenarios)
        within_agree += agree
        prop = agree / p
        lo, hi = wilson_interval(agree, p, confidence)
        n_pass = sum(v == categories[-1] for s in scenarios for v in grid[(s, b)])
        rows.append(
            {
                "bench": b,
                "scenarios_all_replicates_agree": agree,
                "n_scenarios": p,
                "repeatability": prop,
                "ci_low": lo,
                "ci_high": hi,
                "pass_rate": n_pass / (p * r),
            }
        )
    per_bench = pd.DataFrame(rows)

    n_cells = p * o
    lo, hi = wilson_interval(within_agree, n_cells, confidence)
    within_overall = (within_agree, n_cells, within_agree / n_cells, (lo, hi))

    # Between-bench, strict: every observation for the scenario agrees.
    strict = sum(
        len({v for b in benches for v in grid[(s, b)]}) == 1 for s in scenarios
    )
    lo, hi = wilson_interval(strict, p, confidence)
    between_strict = (strict, p, strict / p, (lo, hi))

    # Between-bench, majority verdicts.
    majority = {
        s: [_majority(grid[(s, b)]) for b in benches] for s in scenarios
    }
    maj_agree = sum(
        len(set(majority[s])) == 1 and "__TIE__" not in majority[s]
        for s in scenarios
    )
    lo, hi = wilson_interval(maj_agree, p, confidence)
    between_majority = (maj_agree, p, maj_agree / p, (lo, hi))

    # Fleiss' kappa over every trial (benches x replicates ratings per scenario).
    all_cats = categories + ["__TIE__"]
    counts_all = np.zeros((p, len(categories)))
    for i, s in enumerate(scenarios):
        for b in benches:
            for v in grid[(s, b)]:
                counts_all[i, categories.index(v)] += 1
    k_all = fleiss_kappa(counts_all)

    k_bench = None
    if o >= 3:
        counts_bench = np.zeros((p, len(all_cats)))
        for i, s in enumerate(scenarios):
            for v in majority[s]:
                counts_bench[i, all_cats.index(v)] += 1
        k_bench = fleiss_kappa(counts_bench)

    pair_rows = []
    for b1, b2 in combinations(benches, 2):
        v1 = [majority[s][benches.index(b1)] for s in scenarios]
        v2 = [majority[s][benches.index(b2)] for s in scenarios]
        agree = sum(a == c for a, c in zip(v1, v2))
        lo, hi = wilson_interval(agree, p, confidence)
        pair_rows.append(
            {
                "bench_a": b1,
                "bench_b": b2,
                "agreement": agree / p,
                "ci_low": lo,
                "ci_high": hi,
                "cohen_kappa": cohen_kappa(v1, v2),
            }
        )
    pairwise = pd.DataFrame(pair_rows)
    ck = float(pairwise["cohen_kappa"].iloc[0]) if o == 2 else None

    dis_rows = []
    for s in scenarios:
        obs = {b: grid[(s, b)] for b in benches}
        flat = [v for b in benches for v in obs[b]]
        if len(set(flat)) > 1:
            row: dict[str, Any] = {"scenario": s}
            for b in benches:
                pos = sum(v == categories[-1] for v in obs[b])
                row[str(b)] = f"{pos}/{r} {categories[-1]}"
            row["within_bench_split"] = any(
                len(set(obs[b])) > 1 for b in benches
            )
            dis_rows.append(row)
    disagreements = pd.DataFrame(dis_rows)

    pass_rate = per_bench[["bench", "pass_rate"]].copy()

    return AttributeAgreementResult(
        n_scenarios=p,
        n_benches=o,
        n_replicates=r,
        scenario_col=scenario_col,
        bench_col=bench_col,
        verdict_col=verdict_col,
        categories=categories,
        per_bench_repeatability=per_bench,
        within_bench_overall=within_overall,
        between_bench_strict=between_strict,
        between_bench_majority=between_majority,
        fleiss_kappa_all_trials=k_all,
        fleiss_kappa_bench_verdicts=k_bench,
        cohen_kappa=ck,
        pairwise_cohen_kappa=pairwise,
        bench_pass_rate=pass_rate,
        disagreement_scenarios=disagreements,
        confidence=confidence,
    )


# --------------------------------------------------------------------------
# Bias and linearity against a reference
# --------------------------------------------------------------------------


@dataclass
class BiasLinearityResult:
    """Bias and linearity of a bench against reference (master) values."""

    n: int
    mean_bias: float
    bias_sd: float
    bias_ci: tuple[float, float]
    t_stat: float
    t_p: float
    bias_significant: bool
    slope: float
    intercept: float
    slope_p: float
    intercept_p: float
    r_squared: float
    linearity_significant: bool
    alpha: float
    per_reference: pd.DataFrame


def bias_linearity_study(
    data: pd.DataFrame,
    reference_col: str = "reference_value",
    value_col: str = "value",
    *,
    alpha: float = 0.05,
) -> BiasLinearityResult:
    """AIAG-style bias and linearity study against known reference values.

    Bias is ``value - reference``. Average bias is tested against zero with a
    one-sample t-test. Linearity is assessed by regressing bias on the
    reference value: a non-zero slope means the bias changes across the
    operating range, which is the AIAG definition of a linearity problem.

    This complements the R&R study: R&R quantifies scatter, bias quantifies
    systematic offset from a master. It requires reference values, which for
    a simulation bench means scenarios with an analytically known answer
    (closed-form kinematics, a replayed ground-truth track, or a calibrated
    reference implementation).
    """
    for col in (reference_col, value_col):
        if col not in data.columns:
            raise KeyError(f"column {col!r} not found; have {list(data.columns)}")

    ref = np.asarray(data[reference_col], dtype=float)
    val = np.asarray(data[value_col], dtype=float)
    bias = val - ref
    n = bias.size
    if n < 3:
        raise ValueError("need at least 3 observations for a bias study")
    if np.ptp(ref) == 0:
        raise ValueError(
            "linearity needs at least two distinct reference values spanning "
            "the operating range"
        )
    if np.ptp(bias) == 0:
        raise ValueError(
            "every observation has identical bias, so the bias standard "
            "deviation is zero and the t-test is undefined; supply repeated "
            "measurements that show real scatter"
        )

    mean_bias = float(bias.mean())
    sd = float(bias.std(ddof=1))
    se = sd / math.sqrt(n)
    t_crit = stats.t.ppf(0.5 + (1 - alpha) / 2.0, n - 1)
    ci = (mean_bias - t_crit * se, mean_bias + t_crit * se)
    t_stat, t_p = stats.ttest_1samp(bias, 0.0)

    reg = stats.linregress(ref, bias)
    # p-value for a non-zero intercept.
    resid = bias - (reg.intercept + reg.slope * ref)
    dof = n - 2
    s_err = math.sqrt(float(np.sum(resid**2)) / dof)
    sxx = float(np.sum((ref - ref.mean()) ** 2))
    se_int = s_err * math.sqrt(1.0 / n + ref.mean() ** 2 / sxx)
    t_int = reg.intercept / se_int if se_int > 0 else float("inf")
    p_int = float(2 * stats.t.sf(abs(t_int), dof))

    per_ref = (
        pd.DataFrame({"reference": ref, "bias": bias})
        .groupby("reference")
        .agg(n=("bias", "size"), mean_bias=("bias", "mean"), sd=("bias", "std"))
        .reset_index()
    )

    return BiasLinearityResult(
        n=n,
        mean_bias=mean_bias,
        bias_sd=sd,
        bias_ci=ci,
        t_stat=float(t_stat),
        t_p=float(t_p),
        bias_significant=bool(t_p < alpha),
        slope=float(reg.slope),
        intercept=float(reg.intercept),
        slope_p=float(reg.pvalue),
        intercept_p=p_int,
        r_squared=float(reg.rvalue**2),
        linearity_significant=bool(reg.pvalue < alpha),
        alpha=alpha,
        per_reference=per_ref,
    )
