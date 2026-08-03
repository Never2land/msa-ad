"""Plain-text report rendering.

Reports are plain text on purpose. They are meant to be pasted into a
validation report, diffed between bench builds, and archived next to the
campaign results without a rendering toolchain.
"""

from __future__ import annotations

import math
import textwrap

from .gage_rr import (
    GRR_ACCEPTABLE_PCT,
    GRR_MARGINAL_PCT,
    NDC_MINIMUM,
    AttributeAgreementResult,
    BiasLinearityResult,
    GageRRResult,
    _kappa_label,
)
from .seed_faults import CoverageClaimComparison, SeededFaultResult

__all__ = [
    "render_gage_rr_report",
    "render_attribute_report",
    "render_seeded_fault_report",
    "render_coverage_claim_report",
    "render_bias_report",
]

WIDTH = 78


def _rule(char: str = "-") -> str:
    return char * WIDTH


def _header(title: str) -> list[str]:
    return [_rule("="), title, _rule("=")]


def _pct(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x:6.2f}%"


def _ci(ci: tuple[float, float]) -> str:
    lo, hi = ci
    if math.isnan(lo) or math.isnan(hi):
        return "[   n/a  ,   n/a  ]"
    return f"[{lo:7.4f}, {hi:7.4f}]"


#: Column layout for the fault-listing tables: (column name, width).
FAULT_COLUMNS = [
    ("fault_id", 14),
    ("hazard_id", 14),
    ("hazard_class", 27),
    ("injection_point", 24),
]


def _fault_table(df) -> list[str]:
    """Render a fault listing with fixed column widths that fit the page."""
    lines = ["".join(f"{name:<{w}}" for name, w in FAULT_COLUMNS)]
    for _, row in df.iterrows():
        cells = []
        for name, w in FAULT_COLUMNS:
            text = str(row[name])
            if len(text) > w - 1:
                text = text[: w - 2] + "~"
            cells.append(f"{text:<{w}}")
        lines.append("".join(cells).rstrip())
    return lines


def _wrap(text: str, indent: str = "  ") -> str:
    """Wrap a paragraph to the report width, preserving explicit newlines."""
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(
            textwrap.wrap(
                para.strip(),
                width=WIDTH,
                initial_indent=indent,
                subsequent_indent=indent,
            )
        )
    return "\n".join(out)


def render_gage_rr_report(result: GageRRResult) -> str:
    """Render a crossed ANOVA Gage R&R result as plain text."""
    r = result
    out: list[str] = []
    out += _header("BENCH CHARACTERISATION - GAGE R&R (crossed ANOVA, AIAG MSA)")
    out.append(
        f"Metric              : {r.value_col}\n"
        f"Design              : {r.n_scenarios} scenarios "
        f"x {r.n_benches} benches x {r.n_replicates} replicates "
        f"= {r.n_scenarios * r.n_benches * r.n_replicates} executions\n"
        f"Scenario column     : {r.scenario_col}   "
        f"Bench column: {r.bench_col}"
    )

    out.append("")
    out.append("ANOVA")
    out.append(_rule())
    out.append(
        f"{'source':<26}{'df':>5}{'SS':>13}{'MS':>13}{'F':>10}{'p':>9}"
    )
    for _, row in r.anova.iterrows():
        f_txt = "" if math.isnan(row["f"]) else f"{row['f']:10.4f}"
        p_txt = "" if math.isnan(row["p_value"]) else f"{row['p_value']:9.4f}"
        ms_txt = "" if math.isnan(row["ms"]) else f"{row['ms']:13.6f}"
        out.append(
            f"{row['source']:<26}{int(row['df']):>5}{row['ss']:13.6f}"
            f"{ms_txt:>13}{f_txt:>10}{p_txt:>9}"
        )
    out.append(_rule())
    decision = (
        f"pooled into error (p = {r.interaction_p:.4f} > alpha = "
        f"{r.interaction_alpha})"
        if r.interaction_pooled
        else f"retained (p = {r.interaction_p:.4f} <= alpha = {r.interaction_alpha})"
    )
    out.append(f"Scenario x bench interaction: {decision}")
    out.append(
        "  AIAG MSA tests the interaction at alpha = 0.25 and pools it into"
    )
    out.append("  the error term when it is not significant at that level.")

    out.append("")
    out.append("VARIANCE COMPONENTS")
    out.append(_rule())
    out.append(
        f"{'component':<34}{'variance':>13}{'std dev':>12}{'% of TV':>12}"
    )
    rows = [
        ("Repeatability (EV, equipment)", r.var_repeatability, r.ev, r.pct_ev),
        ("Reproducibility (AV, bench)", r.var_bench + r.var_interaction, r.av, r.pct_av),
        ("   bench effect only", r.var_bench, r.av_bench_only, float("nan")),
        ("   scenario x bench interaction", r.var_interaction, r.interaction, r.pct_interaction),
        ("Gage R&R (GRR)", r.grr**2, r.grr, r.pct_grr),
        ("Scenario variation (PV)", r.var_scenario, r.pv, r.pct_pv),
        ("Total variation (TV)", r.tv**2, r.tv, 100.0),
    ]
    for name, var, sd, pct in rows:
        pct_txt = "" if math.isnan(pct) else _pct(pct)
        out.append(f"{name:<34}{var:13.6f}{sd:12.6f}{pct_txt:>12}")
    out.append(_rule())
    out.append(
        "  Percentages are of total variation (study variation), i.e."
    )
    out.append(
        "  100 * sigma_component / sigma_total. They are ratios of standard"
    )
    out.append("  deviations and therefore do not sum to 100%.")
    out.append(f"  GRR = sqrt(EV^2 + AV^2);  TV = sqrt(GRR^2 + PV^2).")

    if r.pct_grr_tolerance is not None:
        out.append("")
        out.append(
            f"%GRR of tolerance (6*GRR/tol, tol = {r.tolerance:g}): "
            f"{r.pct_grr_tolerance:.2f}%"
        )

    out.append("")
    out.append("ACCEPTANCE (AIAG MSA)")
    out.append(_rule())
    out.append(f"  %GRR = {r.pct_grr:.2f}%   ->   {r.verdict.upper()}")
    out.append(_wrap(r.verdict_text))
    out.append(
        f"    < {GRR_ACCEPTABLE_PCT:.0f}%      acceptable\n"
        f"    {GRR_ACCEPTABLE_PCT:.0f}% - {GRR_MARGINAL_PCT:.0f}%   "
        "marginal / conditionally acceptable\n"
        f"    > {GRR_MARGINAL_PCT:.0f}%      unacceptable"
    )
    ndc_state = "OK" if r.ndc_ok else "FAIL"
    out.append(
        f"  ndc  = floor(1.41 * PV / GRR) = "
        f"floor(1.41 * {r.pv:.4f} / {r.grr:.4f}) = {r.ndc}   ->   {ndc_state}"
    )
    if r.ndc_ok:
        out.append(
            _wrap(
                f"ndc >= {NDC_MINIMUM}: the bench can resolve at least "
                f"{r.ndc} distinct levels of the scenario population."
            )
        )
    else:
        out.append(
            _wrap(
                f"ndc < {NDC_MINIMUM} (AIAG minimum): the bench cannot reliably "
                f"distinguish more than {max(r.ndc, 1)} group(s) of scenarios "
                "on this metric."
            )
        )

    out.append("")
    out.append("PER-BENCH BREAKDOWN")
    out.append(_rule())
    out.append(
        f"{'bench':<12}{'mean':>12}{'bias vs grand':>16}"
        f"{'repeat. SD':>13}{'SD ratio':>11}"
    )
    for _, row in r.per_bench_repeatability.iterrows():
        out.append(
            f"{str(row['bench']):<12}{row['mean']:12.4f}"
            f"{row['bias_vs_grand_mean']:16.4f}"
            f"{row['repeatability_sd']:13.4f}{row['sd_ratio_vs_best']:11.2f}x"
        )
    out.append(_rule())
    if r.levene_p is not None:
        verdict = (
            "within-bench variances differ significantly"
            if r.levene_p < 0.05
            else "no significant difference in within-bench variance"
        )
        out.append(
            f"  Levene test for equal within-bench variance: "
            f"W = {r.levene_stat:.4f}, p = {r.levene_p:.4f}"
        )
        out.append(f"  -> {verdict} (alpha = 0.05).")
    worst = r.per_bench_repeatability.sort_values(
        "repeatability_sd", ascending=False
    ).iloc[0]
    if worst["sd_ratio_vs_best"] >= 1.5:
        out.append(
            _wrap(
                f"Bench {worst['bench']} has the worst repeatability: SD = "
                f"{worst['repeatability_sd']:.4f}, "
                f"{worst['sd_ratio_vs_best']:.2f}x the best bench. The "
                "aggregate EV term averages this away; a single bad bench is "
                "best addressed directly rather than through the pooled figure."
            )
        )
    return "\n".join(out)


def render_attribute_report(result: AttributeAgreementResult) -> str:
    """Render an attribute (pass/fail) agreement result as plain text."""
    a = result
    conf = int(round(a.confidence * 100))
    out: list[str] = []
    out += _header("BENCH CHARACTERISATION - ATTRIBUTE AGREEMENT (pass/fail verdicts)")
    out.append(
        f"Verdict column      : {a.verdict_col}  (categories: {a.categories})\n"
        f"Design              : {a.n_scenarios} scenarios "
        f"x {a.n_benches} benches x {a.n_replicates} replicates "
        f"= {a.n_scenarios * a.n_benches * a.n_replicates} executions\n"
        f"Intervals           : Wilson score, {conf}%"
    )
    out.append("")
    out.append(
        "  Binary verdicts are nominal categories, so this is an agreement\n"
        "  analysis, not a variance decomposition. There is no %GRR and no\n"
        "  ndc here, and there should not be."
    )

    out.append("")
    out.append("WITHIN-BENCH REPEATABILITY  (all replicates of a scenario agree)")
    out.append(_rule())
    out.append(
        f"{'bench':<12}{'agree':>8}{'of':>6}{'proportion':>13}"
        f"{'  ' + str(conf) + '% Wilson CI':<24}{'pass rate':>11}"
    )
    for _, row in a.per_bench_repeatability.iterrows():
        out.append(
            f"{str(row['bench']):<12}"
            f"{int(row['scenarios_all_replicates_agree']):>8}"
            f"{int(row['n_scenarios']):>6}{row['repeatability']:13.4f}"
            f"  {_ci((row['ci_low'], row['ci_high'])):<22}"
            f"{row['pass_rate']:11.4f}"
        )
    k, n, prop, ci = a.within_bench_overall
    out.append(_rule())
    out.append(
        f"{'pooled':<12}{k:>8}{n:>6}{prop:13.4f}  {_ci(ci)}"
    )

    out.append("")
    out.append("BETWEEN-BENCH REPRODUCIBILITY")
    out.append(_rule())
    k, n, prop, ci = a.between_bench_strict
    out.append(
        f"  Strict   (every trial on every bench agrees) : "
        f"{k}/{n} = {prop:.4f}  {_ci(ci)}"
    )
    k, n, prop, ci = a.between_bench_majority
    out.append(
        f"  Majority (bench majority verdicts agree)     : "
        f"{k}/{n} = {prop:.4f}  {_ci(ci)}"
    )
    out.append(
        "  The strict figure also fails when one bench is internally\n"
        "  inconsistent, so it is bounded above by within-bench repeatability.\n"
        "  The majority figure isolates between-bench disagreement."
    )

    out.append("")
    out.append("CHANCE-CORRECTED AGREEMENT")
    out.append(_rule())
    k = a.fleiss_kappa_all_trials
    out.append(
        f"  Fleiss' kappa, all trials pooled       : {k:7.4f}  ({_kappa_label(k)})"
    )
    if a.fleiss_kappa_bench_verdicts is not None:
        kb = a.fleiss_kappa_bench_verdicts
        out.append(
            f"  Fleiss' kappa, bench majority verdicts : {kb:7.4f}  "
            f"({_kappa_label(kb)})"
        )
    if a.cohen_kappa is not None:
        out.append(
            f"  Cohen's kappa (2 benches)             : "
            f"{a.cohen_kappa:7.4f}  ({_kappa_label(a.cohen_kappa)})"
        )
        out.append(
            "  Note: with two raters Fleiss' kappa equals Scott's pi, not\n"
            "  Cohen's kappa; the two differ and both are reported."
        )
    if not a.pairwise_cohen_kappa.empty and a.n_benches > 2:
        out.append("")
        out.append(
            f"{'bench pair':<24}{'agreement':>12}"
            f"{'  ' + str(conf) + '% Wilson CI':<24}{'Cohen kappa':>13}"
        )
        for _, row in a.pairwise_cohen_kappa.iterrows():
            pair = f"{row['bench_a']} vs {row['bench_b']}"
            out.append(
                f"{pair:<24}{row['agreement']:12.4f}"
                f"  {_ci((row['ci_low'], row['ci_high'])):<22}"
                f"{row['cohen_kappa']:13.4f}"
            )
    out.append(
        "  Kappa bands (Landis & Koch 1977) are descriptive conventions, not\n"
        "  acceptance criteria; they are reported as an aid to reading."
    )

    if not a.disagreement_scenarios.empty:
        out.append("")
        out.append("SCENARIOS WITH ANY DISAGREEMENT")
        out.append(_rule())
        df = a.disagreement_scenarios
        cols = [c for c in df.columns if c != "within_bench_split"]
        # The scenario column needs room for long scenario identifiers; the
        # per-bench columns hold short "k/r pass" cells.
        w0 = max(24, max(len(str(v)) for v in df["scenario"]) + 2)
        header = f"{cols[0]:<{w0}}" + "".join(f"{c:<14}" for c in cols[1:])
        header += "within-bench split"
        out.append(header)
        for _, row in df.iterrows():
            line = f"{str(row[cols[0]]):<{w0}}"
            line += "".join(f"{str(row[c]):<14}" for c in cols[1:])
            line += "yes" if row["within_bench_split"] else "no"
            out.append(line)
        out.append(_rule())
        out.append(
            f"  {len(df)} of {a.n_scenarios} scenarios did not produce a "
            "unanimous verdict."
        )
    return "\n".join(out)


def render_seeded_fault_report(result: SeededFaultResult) -> str:
    """Render a seeded-fault coverage-validity result as plain text."""
    s = result
    conf = int(round(s.confidence * 100))
    out: list[str] = []
    out += _header("COVERAGE-CLAIM VERIFICATION - SEEDED KNOWN FAULTS")
    out.append(
        f"Catalogue           : {s.n_catalogue} faults\n"
        f"Executed            : {s.n_seeded}\n"
        f"Expected to detect  : {s.n_expected}  (headline denominator)\n"
        f"Detected            : {s.n_detected}\n"
        f"Intervals           : Wilson score, {conf}%"
    )
    out.append("")
    out.append("COVERAGE-VALIDITY RATIO")
    out.append(_rule())
    out.append(
        f"  detected / seeded-and-expected = {s.n_detected}/{s.n_expected} "
        f"= {s.detection_rate:.4f}"
    )
    out.append(f"  {conf}% Wilson CI: {_ci(s.detection_ci)}")
    out.append(
        f"  {s.n_expected - s.n_detected} seeded fault(s) escaped detection."
    )

    out.append("")
    out.append("BY HAZARD CLASS")
    out.append(_rule())
    out.append(
        f"{'hazard class':<28}{'seeded':>8}{'det.':>6}{'esc.':>6}"
        f"{'rate':>9}{'  ' + str(conf) + '% Wilson CI':<24}{'flag':>6}"
    )
    for _, row in s.by_hazard_class.iterrows():
        flag = "FLAG" if row["below_threshold"] else ""
        out.append(
            f"{str(row['hazard_class']):<28}{int(row['seeded']):>8}"
            f"{int(row['detected']):>6}{int(row['escaped']):>6}"
            f"{row['detection_rate']:9.4f}"
            f"  {_ci((row['ci_low'], row['ci_high'])):<22}{flag:>6}"
        )
    out.append(_rule())
    out.append(
        f"  FLAG = Wilson lower bound below the configured threshold of "
        f"{s.threshold:.2f}."
    )

    if s.any_flagged:
        out.append("")
        out.append("FLAGGED HAZARD CLASSES")
        out.append(_rule())
        for _, row in s.flagged_classes.iterrows():
            out.append(
                f"  {row['hazard_class']}: rate {row['detection_rate']:.4f}, "
                f"CI lower bound {row['ci_low']:.4f} < {s.threshold:.2f}"
            )
            out.append(f"      {row['reason']}")
        out.append(
            "\n  A class can be flagged for two different reasons. Poor measured\n"
            "  detection is a capability problem. A high point estimate with a\n"
            "  low bound is a sample-size problem: seed more faults for that\n"
            "  class before the claim can be defended."
        )

    if not s.escapes.empty:
        out.append("")
        out.append("ESCAPES  (seeded, expected to be detected, not detected)")
        out.append(_rule())
        out += _fault_table(s.escapes)

    if not s.not_executed.empty:
        out.append("")
        out.append("NOT EXECUTED  (in catalogue, absent from campaign results)")
        out.append(_rule())
        out += _fault_table(s.not_executed)
        out.append(_rule())
        out.append(
            f"  {len(s.not_executed)} catalogued fault(s) were never run. These\n"
            "  are excluded from the ratio above rather than counted as\n"
            "  detected or escaped - a detected/seeded ratio computed over\n"
            "  executed faults alone would hide them entirely."
        )

    if not s.unexpected_detections.empty:
        out.append("")
        out.append(
            "DETECTIONS NOT CLAIMED  (expected_detection = False, detected anyway)"
        )
        out.append(_rule())
        out += _fault_table(s.unexpected_detections)
        out.append(_rule())
        out.append(
            "  Not a defect. These faults were injected outside the declared\n"
            "  detection claim and are excluded from the denominator."
        )
    return "\n".join(out)


def render_coverage_claim_report(cmp: CoverageClaimComparison) -> str:
    """Render a claimed-versus-validated coverage comparison as plain text."""
    c = cmp
    conf = int(round(c.confidence * 100))
    out: list[str] = []
    out += _header("CLAIMED VERSUS VALIDATED COVERAGE")
    out.append(f"Claim               : {c.claim_label}")
    out.append(f"Claimed coverage    : {c.claimed_coverage:.4f}")
    out.append(f"Hazards claimed     : {c.n_hazards_claimed}")
    out.append(
        f"  ...with seeded faults : {c.n_hazards_with_seeded_faults}"
    )
    out.append(
        f"  ...unmeasured         : {len(c.hazards_claimed_without_faults)}"
    )
    out.append("")
    out.append(_rule())
    out.append(
        f"  Measured detection rate for claimed hazards: "
        f"{c.n_detected}/{c.n_expected} = {c.measured_rate:.4f}"
    )
    out.append(f"  {conf}% Wilson CI: {_ci(c.measured_ci)}")
    out.append(
        f"  Discrepancy (claimed - measured): {c.discrepancy:+.4f}"
    )
    if c.claim_within_ci:
        out.append(
            f"  The claimed figure of {c.claimed_coverage:.4f} lies inside the "
            f"{conf}% interval;\n"
            "  the seeded-fault evidence is consistent with the claim."
        )
    else:
        out.append(
            f"  The claimed figure of {c.claimed_coverage:.4f} lies OUTSIDE the "
            f"{conf}% interval\n"
            f"  {_ci(c.measured_ci)}. The seeded-fault evidence does not "
            "support the claim\n"
            "  at this sample size."
        )
    out.append(_rule())
    out.append(
        "  These are different quantities and are reported side by side, not\n"
        "  equated. A coverage claim states which hazards have test cases; the\n"
        "  measured rate states how often a fault injected for those hazards is\n"
        "  actually caught. A suite can cover a hazard on paper and still miss a\n"
        "  fault seeded for it. The discrepancy is the size of that gap."
    )

    if c.hazards_claimed_without_faults:
        out.append("")
        out.append(
            "CLAIMED BUT UNMEASURED HAZARDS"
        )
        out.append(_rule())
        for h in c.hazards_claimed_without_faults:
            out.append(f"  {h}")
        out.append(
            _wrap(
                "These hazards contributed nothing to the measured rate: either "
                "no fault was seeded for them, or the faults seeded were never "
                "executed, or they were marked expected_detection = False. For "
                "them the claim is neither supported nor refuted by this "
                "campaign - it is simply untested by fault seeding."
            )
        )

    if not c.by_hazard_class.empty:
        out.append("")
        out.append("PER HAZARD CLASS")
        out.append(_rule())
        out.append(
            f"{'hazard class':<28}{'seeded':>8}{'det.':>6}{'rate':>9}"
            f"{'  ' + str(conf) + '% Wilson CI':<24}{'claimed-meas.':>14}"
        )
        for _, row in c.by_hazard_class.iterrows():
            out.append(
                f"{str(row['hazard_class']):<28}{int(row['seeded']):>8}"
                f"{int(row['detected']):>6}{row['detection_rate']:9.4f}"
                f"  {_ci((row['ci_low'], row['ci_high'])):<22}"
                f"{row['discrepancy']:+14.4f}"
            )
    return "\n".join(out)


def render_bias_report(result: BiasLinearityResult) -> str:
    """Render a bias and linearity study as plain text."""
    b = result
    conf = int(round((1 - b.alpha) * 100))
    out: list[str] = []
    out += _header("BENCH CHARACTERISATION - BIAS AND LINEARITY")
    out.append(f"Observations        : {b.n}")
    out.append("")
    out.append("BIAS  (bench value minus reference value)")
    out.append(_rule())
    out.append(f"  Mean bias      : {b.mean_bias:+.6f}")
    out.append(f"  SD of bias     : {b.bias_sd:.6f}")
    out.append(f"  {conf}% CI on mean : {_ci(b.bias_ci)}")
    out.append(f"  t = {b.t_stat:.4f}, p = {b.t_p:.4f}")
    out.append(
        "  -> bias differs significantly from zero"
        if b.bias_significant
        else "  -> no significant bias detected"
        f" (alpha = {b.alpha})"
    )
    out.append("")
    out.append("LINEARITY  (bias regressed on reference value)")
    out.append(_rule())
    out.append(f"  slope     = {b.slope:+.6f}  (p = {b.slope_p:.4f})")
    out.append(f"  intercept = {b.intercept:+.6f}  (p = {b.intercept_p:.4f})")
    out.append(f"  R^2       = {b.r_squared:.4f}")
    if b.linearity_significant:
        out.append(
            "  -> bias changes significantly across the operating range: the\n"
            "     bench is not equally trustworthy at all reference levels."
        )
    else:
        out.append(
            "  -> no significant linearity problem; bias is consistent across\n"
            "     the reference range examined."
        )
    out.append("")
    out.append("BY REFERENCE VALUE")
    out.append(_rule())
    out.append(f"{'reference':>12}{'n':>6}{'mean bias':>14}{'sd':>12}")
    for _, row in b.per_reference.iterrows():
        sd = "" if math.isnan(row["sd"]) else f"{row['sd']:12.6f}"
        out.append(
            f"{row['reference']:12.4f}{int(row['n']):>6}"
            f"{row['mean_bias']:14.6f}{sd:>12}"
        )
    return "\n".join(out)
