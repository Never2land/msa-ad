"""Coverage-claim verification by seeded known faults.

Production quality engineering passes **known-bad master parts** through an
inspection station on a schedule. If the station accepts a part with a known
defect, the inspection is not detecting what it claims to detect, regardless
of what its documentation says.

This module applies the same idea to an automated-driving validation campaign.
A catalogue of known faults is injected into the system under test and run
through the production campaign. The proportion the campaign actually catches
is the **coverage-validity ratio**: an empirical, measured detection rate that
can be reported alongside - and compared against - any claimed coverage figure.

A claimed coverage figure says "the campaign exercises these hazards". The
coverage-validity ratio says "of the faults we deliberately introduced for
those hazards, this fraction was actually caught". The second is a measurement;
the first is an assertion about the test suite's construction. They answer
different questions, and the gap between them is the interesting quantity.

All proportions carry Wilson score intervals. Per-hazard-class sample sizes in
a real campaign are small (tens, not thousands), and the normal approximation
misbehaves badly near 0 and 1 - exactly where detection rates live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .gage_rr import wilson_interval

__all__ = [
    "FaultCatalogueError",
    "SeededFaultResult",
    "CoverageClaimComparison",
    "analyse_seeded_faults",
    "compare_claimed_coverage",
]

CATALOGUE_REQUIRED = [
    "fault_id",
    "hazard_id",
    "hazard_class",
    "injection_point",
    "expected_detection",
]
RESULTS_REQUIRED = ["fault_id", "detected"]


class FaultCatalogueError(ValueError):
    """Raised when the catalogue or campaign results are malformed."""


def _as_bool(series: pd.Series, name: str) -> pd.Series:
    """Coerce a column of true/false-ish values to bool, strictly."""
    if series.dtype == bool:
        return series
    if pd.api.types.is_numeric_dtype(series):
        bad = set(pd.unique(series.dropna())) - {0, 1, 0.0, 1.0}
        if bad:
            raise FaultCatalogueError(
                f"column {name!r} must be boolean; unexpected values {sorted(bad, key=repr)}"
            )
        return series.astype(bool)
    mapping = {
        "true": True, "t": True, "yes": True, "y": True, "1": True,
        "false": False, "f": False, "no": False, "n": False, "0": False,
    }
    lowered = series.astype(str).str.strip().str.lower()
    bad = sorted(set(lowered) - set(mapping), key=repr)
    if bad:
        raise FaultCatalogueError(
            f"column {name!r} must be boolean; unexpected values {bad}"
        )
    return lowered.map(mapping)


@dataclass
class SeededFaultResult:
    """Measured detection performance of a campaign against seeded faults."""

    n_catalogue: int
    n_seeded: int
    n_expected: int
    n_detected: int
    detection_rate: float
    detection_ci: tuple[float, float]

    by_hazard_class: pd.DataFrame
    escapes: pd.DataFrame
    not_executed: pd.DataFrame
    unexpected_detections: pd.DataFrame
    flagged_classes: pd.DataFrame

    threshold: float
    confidence: float
    merged: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)

    @property
    def any_flagged(self) -> bool:
        return not self.flagged_classes.empty


def analyse_seeded_faults(
    catalogue: pd.DataFrame,
    results: pd.DataFrame,
    *,
    threshold: float = 0.80,
    confidence: float = 0.95,
) -> SeededFaultResult:
    """Compute the coverage-validity ratio for a seeded-fault campaign.

    Parameters
    ----------
    catalogue:
        One row per seeded fault. Required columns: ``fault_id``,
        ``hazard_id``, ``hazard_class``, ``injection_point``,
        ``expected_detection``. ``expected_detection`` is a boolean: faults
        deliberately injected outside the declared ODD, or otherwise not
        claimed to be detectable, are marked ``False`` and excluded from the
        headline ratio (they are reported separately instead of silently
        depressing the score).
    results:
        Campaign outcome, one row per executed fault. Required columns:
        ``fault_id``, ``detected``. Faults present in the catalogue but absent
        here are reported as **not executed** - a coverage gap of a different
        kind, and one that a naive detected/seeded ratio hides completely.
    threshold:
        Detection-rate floor to defend. Any hazard class whose Wilson lower
        confidence bound falls below this value is flagged. Note that this
        flags both genuinely poor detection *and* sample sizes too small to
        support the claim; both are legitimate findings.
    confidence:
        Confidence level for all intervals, default 0.95.

    Returns
    -------
    SeededFaultResult
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be in [0, 1]")

    missing = [c for c in CATALOGUE_REQUIRED if c not in catalogue.columns]
    if missing:
        raise FaultCatalogueError(
            f"fault catalogue is missing required column(s): {missing}. "
            f"Required: {CATALOGUE_REQUIRED}"
        )
    missing = [c for c in RESULTS_REQUIRED if c not in results.columns]
    if missing:
        raise FaultCatalogueError(
            f"campaign results are missing required column(s): {missing}. "
            f"Required: {RESULTS_REQUIRED}"
        )

    cat = catalogue.copy()
    res = results.copy()

    if cat["fault_id"].duplicated().any():
        dup = cat.loc[cat["fault_id"].duplicated(), "fault_id"].unique().tolist()
        raise FaultCatalogueError(f"duplicate fault_id in catalogue: {dup[:10]}")
    if res["fault_id"].duplicated().any():
        dup = res.loc[res["fault_id"].duplicated(), "fault_id"].unique().tolist()
        raise FaultCatalogueError(f"duplicate fault_id in results: {dup[:10]}")

    unknown = set(res["fault_id"]) - set(cat["fault_id"])
    if unknown:
        raise FaultCatalogueError(
            f"campaign results reference {len(unknown)} fault_id(s) absent from "
            f"the catalogue, e.g. {sorted(unknown, key=repr)[:5]}"
        )

    cat["expected_detection"] = _as_bool(
        cat["expected_detection"], "expected_detection"
    )
    res["detected"] = _as_bool(res["detected"], "detected")

    merged = cat.merge(res, on="fault_id", how="left", indicator=True)
    merged["executed"] = merged["_merge"] == "both"
    merged = merged.drop(columns="_merge")

    not_executed = merged.loc[~merged["executed"]].drop(columns=["detected"])
    executed = merged.loc[merged["executed"]].copy()
    executed["detected"] = executed["detected"].astype(bool)

    # Headline ratio: over faults that were executed AND expected to be detected.
    primary = executed.loc[executed["expected_detection"]]
    n_expected = int(len(primary))
    n_detected = int(primary["detected"].sum())
    rate = n_detected / n_expected if n_expected else float("nan")
    ci = wilson_interval(n_detected, n_expected, confidence)

    escapes = primary.loc[~primary["detected"]]
    unexpected = executed.loc[
        (~executed["expected_detection"]) & executed["detected"]
    ]

    rows = []
    for hazard_class, grp in primary.groupby("hazard_class", sort=True):
        n = int(len(grp))
        d = int(grp["detected"].sum())
        lo, hi = wilson_interval(d, n, confidence)
        rows.append(
            {
                "hazard_class": hazard_class,
                "seeded": n,
                "detected": d,
                "escaped": n - d,
                "detection_rate": d / n,
                "ci_low": lo,
                "ci_high": hi,
                "below_threshold": lo < threshold,
            }
        )
    by_class = pd.DataFrame(
        rows,
        columns=[
            "hazard_class", "seeded", "detected", "escaped",
            "detection_rate", "ci_low", "ci_high", "below_threshold",
        ],
    )

    if by_class.empty:
        flagged = by_class.copy()
    else:
        flagged = by_class.loc[by_class["below_threshold"]].copy()
        # Distinguish "detection is genuinely poor" from "n is too small to
        # defend the claim even though every seeded fault was caught".
        flagged["reason"] = np.where(
            flagged["detection_rate"] < threshold,
            "measured detection rate below threshold",
            "point estimate meets threshold but sample too small to defend it",
        )

    return SeededFaultResult(
        n_catalogue=int(len(cat)),
        n_seeded=int(len(executed)),
        n_expected=n_expected,
        n_detected=n_detected,
        detection_rate=rate,
        detection_ci=ci,
        by_hazard_class=by_class,
        escapes=escapes,
        not_executed=not_executed,
        unexpected_detections=unexpected,
        flagged_classes=flagged,
        threshold=threshold,
        confidence=confidence,
        merged=merged,
    )


@dataclass
class CoverageClaimComparison:
    """Claimed coverage versus measured detection for the hazards claimed."""

    claimed_coverage: float
    claim_label: str
    n_hazards_claimed: int
    n_hazards_with_seeded_faults: int
    hazards_claimed_without_faults: list
    n_expected: int
    n_detected: int
    measured_rate: float
    measured_ci: tuple[float, float]
    discrepancy: float
    claim_within_ci: bool
    by_hazard_class: pd.DataFrame
    confidence: float


def compare_claimed_coverage(
    result: SeededFaultResult,
    claimed_coverage: float,
    *,
    claimed_hazard_ids: list[Any] | None = None,
    claim_label: str = "claimed coverage",
) -> CoverageClaimComparison:
    """Compare a claimed coverage figure against the measured detection rate.

    Parameters
    ----------
    result:
        Output of :func:`analyse_seeded_faults`.
    claimed_coverage:
        The figure asserted by the validation argument, as a fraction in
        [0, 1] (e.g. 0.95 for "95% of identified hazards are covered").
    claimed_hazard_ids:
        The hazards the claim actually covers. When omitted, every hazard in
        the catalogue is treated as claimed.
    claim_label:
        Human-readable description of the claim, used in reports.

    Notes
    -----
    A coverage claim and a detection rate are not the same quantity, and this
    function does not pretend otherwise. A claim of the form "95% of hazards
    are covered by the campaign" is a statement about which hazards have test
    cases. The measured rate answers "when a fault for one of those hazards is
    actually present, how often does the campaign notice?". Reporting both is
    the point: a suite can cover a hazard on paper and still fail to detect a
    fault injected for it. The discrepancy reported here is the size of that
    gap, not a refutation of the claim.

    Hazards that are claimed but have no seeded fault at all are listed
    separately: for those, the claim is simply unmeasured.
    """
    if not 0.0 <= claimed_coverage <= 1.0:
        raise ValueError("claimed_coverage must be a fraction in [0, 1]")

    merged = result.merged
    executed = merged.loc[merged["executed"] & merged["expected_detection"]].copy()
    executed["detected"] = executed["detected"].astype(bool)

    all_hazards = sorted(pd.unique(merged["hazard_id"]).tolist(), key=repr)
    if claimed_hazard_ids is None:
        claimed = all_hazards
    else:
        claimed = sorted(set(claimed_hazard_ids), key=repr)

    subset = executed.loc[executed["hazard_id"].isin(claimed)]
    measured_hazards = sorted(pd.unique(subset["hazard_id"]).tolist(), key=repr)
    without = [h for h in claimed if h not in set(measured_hazards)]

    n = int(len(subset))
    d = int(subset["detected"].sum())
    rate = d / n if n else float("nan")
    lo, hi = wilson_interval(d, n, result.confidence)

    rows = []
    if n:
        for hazard_class, grp in subset.groupby("hazard_class", sort=True):
            gn = int(len(grp))
            gd = int(grp["detected"].sum())
            glo, ghi = wilson_interval(gd, gn, result.confidence)
            rows.append(
                {
                    "hazard_class": hazard_class,
                    "seeded": gn,
                    "detected": gd,
                    "detection_rate": gd / gn,
                    "ci_low": glo,
                    "ci_high": ghi,
                    "claimed": claimed_coverage,
                    "discrepancy": claimed_coverage - gd / gn,
                }
            )
    by_class = pd.DataFrame(
        rows,
        columns=[
            "hazard_class", "seeded", "detected", "detection_rate",
            "ci_low", "ci_high", "claimed", "discrepancy",
        ],
    )

    return CoverageClaimComparison(
        claimed_coverage=claimed_coverage,
        claim_label=claim_label,
        n_hazards_claimed=len(claimed),
        n_hazards_with_seeded_faults=len(measured_hazards),
        hazards_claimed_without_faults=without,
        n_expected=n,
        n_detected=d,
        measured_rate=rate,
        measured_ci=(lo, hi),
        discrepancy=claimed_coverage - rate if n else float("nan"),
        claim_within_ci=bool(lo <= claimed_coverage <= hi) if n else False,
        by_hazard_class=by_class,
        confidence=result.confidence,
    )
