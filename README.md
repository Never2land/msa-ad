# msa-ad

**Measurement System Analysis for Automated-Driving Validation.**

Gage R&R, attribute agreement, and seeded-fault coverage verification for
simulation, hardware-in-the-loop (HIL) and fault-injection benches.

Python ≥ 3.10. Depends on numpy, scipy and pandas only. Apache-2.0.

---

## What this is

Automated-driving safety cases rest on simulation, HIL and fault-injection
benches rather than on road mileage. Kalra and Paddock (RAND, RR-1478-RC, 2016)
estimated what statistical demonstration by driving would actually cost: on the
order of 275 million miles driven without a fatality to show, with 95%
confidence, a fatality rate below the contemporary human benchmark, and
billions of miles to show a modest improvement over it. Those distances are not
drivable inside a development programme. The consequence is that the bench, not
the road, is where the evidence comes from.

That makes the bench **the instrument of record**. And an instrument of record
is something regulated manufacturing already knows how to treat: before you
trust what a gauge tells you about a part, you characterise the gauge.

Regulated automotive production does this under Measurement System Analysis
(AIAG MSA): gage repeatability and reproducibility studies, bias and linearity
against a certified master, and stability monitoring over time. Production
quality engineering also does something else that transfers directly — it
passes **known-bad master parts** through inspection stations on a schedule. If
the station accepts a part with a known defect, the inspection is not detecting
what it claims to detect, whatever its documentation says.

`msa-ad` transfers both practices onto automated-driving validation benches.

### Two components

**1. Bench characterisation.** How much of an observed scenario verdict
originates in the apparatus rather than in the system under test?

The mapping onto AIAG's crossed Gage R&R design is direct:

| AIAG MSA        | Automated-driving bench                              |
| --------------- | ---------------------------------------------------- |
| part            | scenario                                             |
| appraiser       | bench (simulation host, HIL rig, fault-injection rig)|
| trial/replicate | repeated execution, typically varying the random seed|
| measurement     | safety-margin metric, or pass/fail verdict           |

**2. Coverage-claim verification.** A catalogue of known faults is injected and
run through the *production* campaign — not a special campaign built to catch
them. The fraction actually caught is a measured detection rate that can be
reported alongside any coverage claim.

---

## The gap this addresses

Simulation credibility is not an unregulated area, and it would be misleading to
begin as though it were. Several instruments address it directly, and one of them
is binding law.

**Commission Implementing Regulation (EU) 2022/1426**, Annex III Part 4, has
applied in the European Union since September 2022. It is titled, verbatim,
*"Principles for credibility assessment for using virtual toolchain in ADS
validation"*, and it is considerably more specific than most people outside
European type approval expect:

> §3.4.5.1 — "**The quantitative process** of determining the degree to which a
> model or a simulation is an accurate representation of the real world from the
> perspective of the intended uses of the M&S requires the selection and
> definition of several elements."

> §3.2.6.4 — "(a) Stochastic models shall be characterised **in terms of their
> variance** (b) Stochastic models shall be ensured the possibility of
> **deterministic re-execution**"

> §3.4.5.9.2 — "The manufacturer shall demonstrate to have appropriately
> estimated the critical model's inputs by means of robust techniques such as
> **multiple repetitions** for the assessment of the quantity"

> §3.4.5.9.5 — the manufacturer "shall aim to distinguish between the
> **aleatory** component of the uncertainty (which can only be estimated but not
> reduced) and the **epistemic** uncertainty deriving from the lack of knowledge"

That is run-to-run variance, repeated execution, deterministic replay, and a
precision-versus-bias decomposition — in mandatory form. **UN Regulation No. 157**,
Annex 4 ¶4.2 separately requires manufacturers to demonstrate "the validation
performed for the simulation tool chain (correlation of the outcome with physical
tests)", cross-referring to Schedule 8 of the 1958 Agreement.

So the interesting question is not whether anyone has thought about this. They
have, and in more detail than the ISO functional-safety standards suggest.

### What those instruments leave open

**None of them defines the metric or the threshold.**

EU 2022/1426 §3.4.5.5.1 provides that *"the requirement for the correlation
threshold is defined during the M&S analysis"* — that is, by the manufacturer
whose toolchain is being assessed. Schedule 8 of the 1958 Agreement requires only
that *"comparability of the test results shall be proven"*, and prescribes no
tolerance, no acceptance band, and no protocol by which comparability is judged.

The consequence is worth stating plainly: **two manufacturers can both hold
compliant credibility evidence and there is no basis on which to compare them.**
Each defined its own threshold. Neither figure means the same thing as the other.

This is the difference between requiring that something be assessed and
specifying how to measure it. Production metrology settled the equivalent
question decades ago with AIAG MSA — a named protocol, a variance-component
decomposition, and acceptance bands (%GRR under 10 acceptable, 10–30 conditional,
over 30 unacceptable; ndc at least 5) that mean the same thing in every plant
that uses them. Nothing of that kind exists for an automated-driving bench.

**That specific absence is what this package is about**: not credibility
assessment in general, which is regulated, but a defined protocol producing
figures that are comparable between organisations.

### The obvious objection: isn't this ISO 26262-8 Clause 11?

ISO 26262-8 Clause 11, "Confidence in the use of software tools", addresses
exactly the worry that a tool used in safety-related development might cause
harm. It classifies a tool by **Tool Impact** — can the tool introduce, or fail
to detect, an error in the safety-related item being developed? — and by **Tool
error Detection** — how likely is such an error to be prevented or detected?
These combine into a **Tool Confidence Level**, and where the level demands it,
the clause requires qualification evidence: increased confidence from use,
evaluation of the tool development process, validation of the tool, or
development in accordance with a safety standard.

That is the right question to ask, and it is genuinely adjacent to what this
repository is about. A simulation bench that silently mis-integrates vehicle
dynamics is precisely a tool that can fail to detect an error, and Clause 11 is
where you are supposed to worry about it.

But the *output* of Clause 11 is a classification plus a body of qualification
evidence. It establishes that a tool is fit for its purpose in the development
process. It does not, in itself, produce the quantity a measurement engineer
would ask for: **a number saying how much of the variation in an observed
scenario outcome came from the bench rather than from the system under test —
on this metric, for this scenario set, at this point in time.**

Concretely, a bench can hold valid tool-qualification evidence and still
exhibit all of the following:

- a repeatability term large enough that repeated executions of the same
  scenario, differing only in random seed, straddle a pass/fail threshold;
- a systematic offset between two nominally identical HIL rigs, so that a
  scenario's verdict depends on which rig happened to run it;
- a number of distinct categories (ndc) below 5 on a safety-margin metric,
  meaning the bench cannot resolve five distinguishable levels of that metric
  across the scenario population it is being used to assess.

None of those are tool defects in the Clause 11 sense. The tool is doing what
it was qualified to do. They are **measurement system** properties, and AIAG
MSA exists precisely to quantify them. Tool qualification asks *is this tool
fit to be used?*; measurement system analysis asks *how much of what it just
told me was the tool?* Both are worth answering, and answering one does not
answer the other.

The production analogy is exact. A gauge on a regulated line must be both
**approved and calibrated** — which is what tool qualification corresponds to —
**and** subjected to a Gage R&R study, which is what this package corresponds to.
They are separate activities producing separate artefacts, and no plant I have
worked in would accept the first as a substitute for the second.

One consequence worth drawing out, because it points at how this would actually
be adopted rather than at a dispute: Clause 11's **method 1c, "validation of the
software tool"**, requires test cases derived from the tool's use cases and
evidence that it meets its requirements. It does not say how that evidence should
be quantified. **An MSA study is a legitimate way to discharge 1c**, and a more
informative one than a pass/fail test report, because it yields a number that can
be trended and compared rather than a verdict that cannot. If you already run
Clause 11 on your benches, this is meant to slot into it, not to compete with it.

### The same distinction, applied to coverage

A coverage figure states which hazards, scenarios or ODD regions the campaign
has test cases for. It is an assertion about the *construction of the test
suite*. It is not evidence that a fault belonging to one of those hazards would
actually be caught if it were present.

Production quality engineering does not accept that assertion either. It seeds
known defects and measures what fraction the inspection station catches. The
measured detection rate and the coverage claim are different quantities, and
this package reports them side by side rather than equating them. The gap
between them is the interesting number.

### This is a claim inviting correction

The claim I am making is narrow, and I want to state its boundaries rather than
let a reader discover them.

**What I am not claiming:** that simulation credibility is unaddressed. It is
addressed, bindingly, by EU 2022/1426 Annex III Part 4 and by UN-R157 Annex 4
with Schedule 8, and conceptually by NASA-STD-7009 and the ASME V&V series. An
earlier draft of this README understated that, and it was wrong to.

**What I am claiming:** that no published protocol applies the production
measurement-system-analysis method — a variance-component decomposition into
repeatability and reproducibility with named acceptance bands, a linearity and
stability study across the operating range, calibrated seeded-fault positive
controls, and reproducibility across independent facilities under a common
protocol — as an integrated qualification of an automated-driving validation
bench treated as a measurement instrument. And that because no instrument defines
the metric, credibility evidence is not comparable between organisations.

"I have not found it" remains a weak form of argument and the surrounding space
is large. Ground I am aware of, and which anyone evaluating this should check:

- **Commission Implementing Regulation (EU) 2022/1426**, Annex III Part 4 —
  the most directly on-point instrument I know of;
- **UN-R157** Annex 4 ¶4.2 and **Schedule 8 of the 1958 Agreement**, "General
  conditions for virtual testing methods";
- **UNECE NATM** (New Assessment/Test Method) master document;
- ISO 26262 (functional safety), ISO 21448 (SOTIF), and ISO 34502 Annex F,
  "Qualification of virtual test platforms" — which is informative rather than
  normative, and I have not read its body text;
- UL 4600, which discusses validation and simulation credibility — I have not
  read it;
- NASA-STD-7009 on models-and-simulations credibility, and the ASME V&V series
  on verification and validation in computational modelling, including V&V 40's
  risk-informed credibility framework;
- China's GB 44721 and GB/T 47025 series on ADS simulation test methods;
- **ASAM's "Quantifying Simulation Quality" project** (P_2025_04), running since
  December 2025, whose stated premise is that no standardised metrics currently
  exist for assessing simulation quality — if that project publishes something
  that does what is described here, this package should defer to it;
- the software-engineering mutation-testing literature, the closest analogue I
  know of to the seeded-fault component.

If any of these — or anything else — already prescribes a variance-decomposed
repeatability and reproducibility characterisation of a validation bench with
defined acceptance criteria, **please open an issue**. I would much rather cite
prior art than duplicate it, and a pointer that collapses this argument is more
useful to me than agreement with it. That has already happened once: EU 2022/1426
is in this list because looking for the counter-argument found it.

---

## Install and run

```bash
git clone <this repository>
cd msa-ad
python -m pip install -e .          # numpy, scipy, pandas
python example/run_example.py       # end-to-end worked example
```

Tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Regenerate the synthetic example data (deterministic, fixed seed):

```bash
python example/run_example.py --regenerate
```

### Minimal use

```python
import pandas as pd
from msa_ad import (
    gage_rr_anova, attribute_agreement,
    analyse_seeded_faults, compare_claimed_coverage,
    render_gage_rr_report, render_seeded_fault_report,
)

runs = pd.read_csv("example/bench_runs.csv")

# Continuous safety-margin metric -> crossed ANOVA Gage R&R
grr = gage_rr_anova(runs, scenario_col="scenario_id",
                    bench_col="bench_id", value_col="min_ttc_s")
print(render_gage_rr_report(grr))
print(grr.pct_grr, grr.ndc, grr.verdict)

# Binary pass/fail verdicts -> attribute agreement, NOT variance decomposition
attr = attribute_agreement(runs, verdict_col="verdict")

# Seeded faults -> measured detection rate with Wilson intervals
seeded = analyse_seeded_faults(
    pd.read_csv("example/fault_catalogue.csv"),
    pd.read_csv("example/campaign_results.csv"),
    threshold=0.80,
)
claim = compare_claimed_coverage(seeded, claimed_coverage=0.95)
```

Passing the binary `verdict` column to `gage_rr_anova` raises
`BinaryDataError` rather than returning a meaningless `%GRR`. That guard is a
deliberate feature; see "Statistical notes" below.

---

## Worked example

**All data in this example is synthetic.** It is generated by `msa_ad.datagen`
from a fixed seed and is not measured data from any bench, programme or
vehicle. It is constructed to contain findings, because a demonstration in
which everything passes demonstrates nothing: one bench (`HIL-C`) has roughly
four times the repeatability standard deviation of the others, several
scenarios sit near the pass/fail threshold, and one hazard class detects
poorly.

Output of `python example/run_example.py`, lightly elided where marked:

### 1a. Bench characterisation — continuous metric

```
==============================================================================
BENCH CHARACTERISATION - GAGE R&R (crossed ANOVA, AIAG MSA)
==============================================================================
Metric              : min_ttc_s
Design              : 15 scenarios x 3 benches x 3 replicates = 135 executions
Scenario column     : scenario_id   Bench column: bench_id

ANOVA
------------------------------------------------------------------------------
source                       df           SS           MS         F        p
scenario_id (scenario)       14    64.627089     4.616221   56.7764
bench_id (bench)              2     1.470985     0.735493    9.0461
scenario x bench             28     2.276546     0.081305    1.5787   0.0554
repeatability (error)        90     4.635143     0.051502
total                       134    73.009763
------------------------------------------------------------------------------
Scenario x bench interaction: retained (p = 0.0554 <= alpha = 0.25)
  AIAG MSA tests the interaction at alpha = 0.25 and pools it into
  the error term when it is not significant at that level.

VARIANCE COMPONENTS
------------------------------------------------------------------------------
component                              variance     std dev     % of TV
Repeatability (EV, equipment)          0.051502    0.226940      29.80%
Reproducibility (AV, bench)            0.024472    0.156435      20.54%
   bench effect only                   0.014537    0.120572
   scenario x bench interaction        0.009935    0.099672      13.09%
Gage R&R (GRR)                         0.075974    0.275633      36.20%
Scenario variation (PV)                0.503879    0.709845      93.22%
Total variation (TV)                   0.579853    0.761481     100.00%
------------------------------------------------------------------------------
  Percentages are of total variation (study variation), i.e.
  100 * sigma_component / sigma_total. They are ratios of standard
  deviations and therefore do not sum to 100%.
  GRR = sqrt(EV^2 + AV^2);  TV = sqrt(GRR^2 + PV^2).

ACCEPTANCE (AIAG MSA)
------------------------------------------------------------------------------
  %GRR = 36.20%   ->   UNACCEPTABLE
  %GRR = 36.2% > 30% - measurement system unacceptable (AIAG MSA); it needs
  improvement before its verdicts can be relied upon.
    < 10%      acceptable
    10% - 30%   marginal / conditionally acceptable
    > 30%      unacceptable
  ndc  = floor(1.41 * PV / GRR) = floor(1.41 * 0.7098 / 0.2756) = 3   ->   FAIL
  ndc < 5 (AIAG minimum): the bench cannot reliably distinguish more than 3
  group(s) of scenarios on this metric.

PER-BENCH BREAKDOWN
------------------------------------------------------------------------------
bench               mean   bias vs grand   repeat. SD   SD ratio
HIL-A             1.9766         -0.0134       0.0845       1.00x
HIL-B             1.8694         -0.1206       0.1046       1.24x
HIL-C             2.1241          0.1340       0.3693       4.37x
------------------------------------------------------------------------------
  Levene test for equal within-bench variance: W = 36.1345, p = 0.0000
  -> within-bench variances differ significantly (alpha = 0.05).
  Bench HIL-C has the worst repeatability: SD = 0.3693, 4.37x the best bench.
  The aggregate EV term averages this away; a single bad bench is best
  addressed directly rather than through the pooled figure.
```

The finding: 36.2% of the total variation in observed minimum TTC comes from
the measurement system rather than from the scenarios. `ndc = 3` says the setup
can distinguish about three levels of safety margin across this scenario set —
below the AIAG minimum of 5. The per-bench breakdown localises it: `HIL-C` is
carrying it, at 4.37x the repeatability SD of the best bench.

### 1b. The guard

```
BinaryDataError raised, as it should be:

    Column 'verdict' looks like a binary / categorical pass-fail
    verdict (distinct values observed: ['fail', 'pass']).

    Crossed ANOVA Gage R&R decomposes the variance of a measurement on
    a continuous scale into repeatability, reproducibility and part
    variation. A pass/fail verdict is a nominal category, so:
      - its 'variance' has no physical units and the components are not
        interpretable as measurement error;
      - %GRR cannot be compared against the AIAG 10% / 30% thresholds;
      - ndc, which counts resolvable levels of a continuous scale, is
        meaningless for two categories.
    For a Bernoulli variable the variance is a deterministic function of
    the mean, p*(1-p). A bench that simply fails more scenarios would
    therefore appear to have different 'repeatability' purely because
    its pass rate differs, which is not a property of the apparatus.

    Use msa_ad.gage_rr.attribute_agreement() instead. [...]
```

### 1c. Bench characterisation — binary verdicts

```
==============================================================================
BENCH CHARACTERISATION - ATTRIBUTE AGREEMENT (pass/fail verdicts)
==============================================================================
Verdict column      : verdict  (categories: ['fail', 'pass'])
Design              : 15 scenarios x 3 benches x 3 replicates = 135 executions
Intervals           : Wilson score, 95%

  Binary verdicts are nominal categories, so this is an agreement
  analysis, not a variance decomposition. There is no %GRR and no
  ndc here, and there should not be.

WITHIN-BENCH REPEATABILITY  (all replicates of a scenario agree)
------------------------------------------------------------------------------
bench          agree    of   proportion  95% Wilson CI           pass rate
HIL-A             14    15       0.9333  [ 0.7018,  0.9881]         0.7111
HIL-B             12    15       0.8000  [ 0.5481,  0.9295]         0.6444
HIL-C             11    15       0.7333  [ 0.4805,  0.8910]         0.7333
------------------------------------------------------------------------------
pooled            37    45       0.8222  [ 0.6867,  0.9071]

BETWEEN-BENCH REPRODUCIBILITY
------------------------------------------------------------------------------
  Strict   (every trial on every bench agrees) : 8/15 = 0.5333  [ 0.3012,  0.7519]
  Majority (bench majority verdicts agree)     : 11/15 = 0.7333  [ 0.4805,  0.8910]
  The strict figure also fails when one bench is internally
  inconsistent, so it is bounded above by within-bench repeatability.
  The majority figure isolates between-bench disagreement.

CHANCE-CORRECTED AGREEMENT
------------------------------------------------------------------------------
  Fleiss' kappa, all trials pooled       :  0.5797  (moderate)
  Fleiss' kappa, bench majority verdicts :  0.5673  (moderate)

bench pair                 agreement  95% Wilson CI           Cohen kappa
HIL-A vs HIL-B                0.9333  [ 0.7018,  0.9881]           0.8421
HIL-A vs HIL-C                0.7333  [ 0.4805,  0.8910]           0.3182
HIL-B vs HIL-C                0.8000  [ 0.5481,  0.9295]           0.5263
  Kappa bands (Landis & Koch 1977) are descriptive conventions, not
  acceptance criteria; they are reported as an aid to reading.

SCENARIOS WITH ANY DISAGREEMENT
------------------------------------------------------------------------------
scenario                HIL-A         HIL-B         HIL-C         within-bench split
CUT_IN_60KPH            0/3 pass      0/3 pass      2/3 pass      yes
CYCLIST_OVERTAKE        3/3 pass      3/3 pass      2/3 pass      yes
MERGE_DENSE             3/3 pass      1/3 pass      1/3 pass      yes
ONCOMING_INTRUSION      0/3 pass      0/3 pass      3/3 pass      no
PED_CROSS_OCCLUDED      2/3 pass      2/3 pass      3/3 pass      yes
STATIONARY_OBSTACLE     3/3 pass      3/3 pass      1/3 pass      yes
TRAFFIC_LIGHT_DILEMMA   3/3 pass      2/3 pass      3/3 pass      yes
------------------------------------------------------------------------------
  7 of 15 scenarios did not produce a unanimous verdict.
```

The finding: only 8 of 15 scenarios produced a unanimous verdict across all
benches and replicates. `ONCOMING_INTRUSION` is the sharpest case — each bench
is internally perfectly consistent, and they still disagree with each other:
`HIL-C` passes it 3/3 while the other two fail it 3/3. Consistency within a
bench is not agreement between benches, and reporting only the former would
have hidden this.

### 2a. Coverage-claim verification

```
==============================================================================
COVERAGE-CLAIM VERIFICATION - SEEDED KNOWN FAULTS
==============================================================================
Catalogue           : 129 faults
Executed            : 124
Expected to detect  : 120  (headline denominator)
Detected            : 99
Intervals           : Wilson score, 95%

COVERAGE-VALIDITY RATIO
------------------------------------------------------------------------------
  detected / seeded-and-expected = 99/120 = 0.8250
  95% Wilson CI: [ 0.7472,  0.8826]
  21 seeded fault(s) escaped detection.

BY HAZARD CLASS
------------------------------------------------------------------------------
hazard class                  seeded  det.  esc.     rate  95% Wilson CI           flag
actuation_fault                   25    24     1   0.9600  [ 0.8046,  0.9929]
perception_false_negative         40    22    18   0.5500  [ 0.3983,  0.6929]      FLAG
planning_timing                   30    28     2   0.9333  [ 0.7868,  0.9815]      FLAG
sensor_dropout                    25    25     0   1.0000  [ 0.8668,  1.0000]
------------------------------------------------------------------------------
  FLAG = Wilson lower bound below the configured threshold of 0.80.

FLAGGED HAZARD CLASSES
------------------------------------------------------------------------------
  perception_false_negative: rate 0.5500, CI lower bound 0.3983 < 0.80
      measured detection rate below threshold
  planning_timing: rate 0.9333, CI lower bound 0.7868 < 0.80
      point estimate meets threshold but sample too small to defend it

  A class can be flagged for two different reasons. Poor measured
  detection is a capability problem. A high point estimate with a
  low bound is a sample-size problem: seed more faults for that
  class before the claim can be defended.

[escape listing, 21 rows, elided]
[not-executed listing, 5 rows, elided]
[detections outside the claim, 2 rows, elided]
```

Two different findings, deliberately. `perception_false_negative` is a
capability problem: 18 of 40 seeded faults walked through the campaign
undetected. `planning_timing` is a *sample size* problem — 28 of 30 is a good
result, but 30 seeded faults cannot support a 0.80 lower bound. Distinguishing
these matters, because the corrective action is completely different: fix the
campaign in the first case, seed more faults in the second.

### 2b. Claimed versus validated

```
==============================================================================
CLAIMED VERSUS VALIDATED COVERAGE
==============================================================================
Claim               : 95% of identified hazards covered by the Q2 campaign
Claimed coverage    : 0.9500
Hazards claimed     : 33
  ...with seeded faults : 24
  ...unmeasured         : 9

------------------------------------------------------------------------------
  Measured detection rate for claimed hazards: 99/120 = 0.8250
  95% Wilson CI: [ 0.7472,  0.8826]
  Discrepancy (claimed - measured): +0.1250
  The claimed figure of 0.9500 lies OUTSIDE the 95% interval
  [ 0.7472,  0.8826]. The seeded-fault evidence does not support the claim
  at this sample size.
------------------------------------------------------------------------------
  These are different quantities and are reported side by side, not
  equated. A coverage claim states which hazards have test cases; the
  measured rate states how often a fault injected for those hazards is
  actually caught. A suite can cover a hazard on paper and still miss a
  fault seeded for it. The discrepancy is the size of that gap.
```

### Summary

```
* Gage R&R on min_ttc_s: %GRR = 36.2% (unacceptable), ndc = 3 (AIAG minimum 5: NOT met).
* Bench HIL-C dominates the repeatability term: SD = 0.369 s, 4.4x the best bench.
* Attribute agreement: between-bench strict reproducibility = 0.533, Fleiss' kappa = 0.580.
* Coverage-validity ratio: 99/120 = 0.825 [0.747, 0.883].
* Hazard classes flagged at threshold 0.80: ['perception_false_negative', 'planning_timing'].
* Claimed coverage 0.95 vs measured 0.825: discrepancy +0.125, claim outside the 95% interval.
* 5 catalogued fault(s) were never executed and are excluded from the ratio.
```

---

## Statistical notes

### Continuous metrics: crossed ANOVA Gage R&R

Balanced crossed design, *p* scenarios × *o* benches × *r* replicates,
following the ANOVA method of AIAG MSA 4th edition.

Variance components are estimated from the mean squares. The appraiser
component subtracts the interaction mean square,
`var_bench = (MS_bench − MS_interaction) / (p·r)`, so the bench term is not
inflated by interaction or residual variance. The interaction is tested at
**alpha = 0.25** (AIAG's value, deliberately liberal) and pooled into the error
term when it is not significant, after which the components are recomputed from
the pooled residual. Negative moment estimates are clamped to zero.

Reported: `EV`, `AV`, the interaction term, `GRR = sqrt(EV² + AV²)`, `PV`, `TV`,
each as a percentage of total variation, and
`ndc = floor(1.41 × PV / GRR)`.

Following AIAG, reproducibility (`AV`) includes the scenario-by-bench
interaction; the pure bench term is reported separately as `av_bench_only`.
When the interaction is pooled away, the two coincide.

Acceptance, printed explicitly with every report:

| %GRR      | AIAG interpretation                                     |
| --------- | ------------------------------------------------------- |
| < 10%     | acceptable                                              |
| 10% – 30% | conditionally acceptable, depending on application importance, cost of the measurement device, and cost of repair |
| > 30%     | unacceptable                                            |

with `ndc ≥ 5` required.

The **per-bench breakdown** is not part of standard AIAG output but is included
because it is what actually localises a problem. The pooled `EV` term averages a
single misbehaving bench together with two good ones; the per-bench
repeatability SDs and a Levene test for equal within-bench variance do not.

### Binary verdicts: attribute agreement, not variance decomposition

Pass/fail verdicts are nominal categories. Running them through a variance
decomposition produces numbers that look like a Gage R&R result and mean
nothing: `%GRR` has no interpretable scale, the AIAG thresholds do not apply,
and `ndc` counts resolvable levels of a continuum that does not exist. Worse,
because a Bernoulli variance is `p(1−p)`, a bench that simply fails more
scenarios would appear to have different "repeatability" purely as an artefact
of its pass rate.

`gage_rr_anova` therefore **raises `BinaryDataError`** on binary or
low-cardinality input, with an explanation of why and a pointer to the
attribute path. It detects boolean dtype, `{0, 1}` coding, string verdicts, and
any column with two or fewer distinct values. An `allow_low_cardinality=True`
escape hatch exists for genuinely continuous metrics that happen to be sparse
in a given sample.

`attribute_agreement` reports, each with a Wilson score interval:

- **within-bench repeatability** — proportion of scenarios where all replicates
  on that bench agree, per bench and pooled;
- **between-bench reproducibility, strict** — proportion of scenarios where
  every observation on every bench agrees. Deliberately conservative: it also
  fails when a single bench is internally inconsistent, so it is bounded above
  by within-bench repeatability;
- **between-bench reproducibility, majority** — each bench reduced to its
  majority verdict first, which isolates between-bench disagreement from
  within-bench inconsistency. A bench whose replicates split evenly is treated
  as its own state and never counts as agreeing;
- **Fleiss' kappa** over all trials and over bench majority verdicts, and
  **pairwise Cohen's kappa**.

Note that with two raters Fleiss' kappa reduces to **Scott's pi**, not Cohen's
kappa. They differ, and both are reported for the two-bench case rather than
one being passed off as the other.

### Why Wilson intervals everywhere

Every proportion in this package carries a Wilson score interval rather than a
normal (Wald) approximation. Seeded-fault campaigns and bench studies produce
small samples, and detection rates live near 1 — exactly where the Wald
interval misbehaves. At 0 or *n* successes it collapses to zero width, implying
certainty from a handful of observations, and near the boundaries it can put
bounds outside [0, 1].

This is not a cosmetic choice. In the example above, `sensor_dropout` detected
25 of 25 seeded faults. The Wald interval for that is `[1.0, 1.0]`. The Wilson
interval is `[0.867, 1.000]` — which correctly says that 25 successes do not
establish a detection rate above 0.867, let alone 1.0.

### Bias and linearity

`bias_linearity_study` compares bench output against known reference values:
mean bias with a one-sample *t*-test, and linearity by regressing bias on the
reference value, so that a bias which changes across the operating range is
distinguished from a constant offset.

This requires reference values, which for a simulation bench means scenarios
with an analytically known answer — closed-form kinematics, a replayed
ground-truth track, or a calibrated reference implementation. That is a real
constraint and is why this component is smaller than the other two.

---

## Correctness

`pytest` — 168 tests. The suite asserts the mathematics against independently
known values, not merely that functions return without raising:

- **Variance components** are checked against a 2×2×2 crossed design worked
  through by hand in `tests/test_gage_rr.py`, with every sum of squares, mean
  square and variance component written out in the comments so a reader can
  verify the expected numbers with a pencil. Both the pooled and the unpooled
  interaction paths are covered.
- **Sums of squares** are additionally cross-checked against an independent
  least-squares model-comparison computation over randomised designs. That is a
  different algebraic route from the closed-form cell-margin formulas the
  module uses, so an error in one path cannot hide in the other.
- The **AIAG MSA 4th edition gage study data set** reproduces the published
  scenario, appraiser and equipment sums of squares (88.3619, 3.1673, 2.7589)
  and yields %GRR = 27.86% with ndc = 4.
- **Wilson intervals** are asserted against published values — 0/10 →
  `[0, 0.2775]`, 15/20 → `[0.5313, 0.8881]` — against a restatement of the
  formula, and for the symmetry and boundary properties that distinguish them
  from Wald.
- **Fleiss' kappa** is asserted against two tables whose kappa is derived
  exactly in the comments (1/3 and 7/12), and against the Fleiss (1971)
  30-subject table. **Cohen's kappa** uses the standard 2×2 example giving 0.40.
  A test records that Fleiss with two raters equals Scott's pi.
- **Guard tests** cover binary rejection in seven encodings and assert the
  error message explains *why* rather than only *that*.
- Tests assert that the bundled example actually contains findings, so the
  demonstration cannot silently decay into one where everything passes.

---

## Status and limitations

Please read this section before citing or relying on anything here.

- **This is a proposed method and a reference implementation. It is not a
  standard.** It has not been through any standardisation body, industry
  consortium or formal review.
- **It has not been validated against industrial data.** I have not run it
  against a production automated-driving validation programme, and I make no
  claim about how it behaves on one.
- **The bundled example data is entirely synthetic.** It is generated from a
  fixed seed by `msa_ad.datagen` and was constructed to contain the findings it
  reports. It is not measured data from any bench, programme or vehicle, and no
  number in it should be read as an observation about any real system.
- **No industrial adoption is claimed.** No organisation uses this. No
  benchmarks are asserted beyond what the code computes on the synthetic data
  shipped with it.
- **The gap argument in this README is a claim, not an established finding.** It
  is my reading of what ISO 26262 and ISO 21448 do and do not prescribe. I may
  be wrong, and I would like to know if I am.
- **Scope limits.** The crossed ANOVA requires a balanced design with no empty
  cells; nested and unbalanced designs are not implemented. Stability
  monitoring — the control-chart component of AIAG MSA, tracking a bench over
  time — is described as part of the method but is **not implemented here**.
  The bias and linearity study requires reference values that many benches will
  not have.
- **Statistical caveats.** The interaction pooling rule at alpha = 0.25 is
  AIAG's convention, not a derived optimum. `ndc` is a rule of thumb, not an
  inferential statistic. The kappa bands quoted in reports are Landis and Koch's
  descriptive conventions and are not acceptance criteria. The Wilson intervals
  on agreement proportions treat scenarios as independent, which repeated
  scenario families may violate.

---

## References

- AIAG, *Measurement Systems Analysis Reference Manual*, 4th edition,
  Automotive Industry Action Group, 2010. Source of the crossed ANOVA Gage R&R
  method, the %GRR acceptance bands, `ndc`, and attribute agreement analysis.
- ISO 26262:2018, *Road vehicles — Functional safety.* Part 8 ("Supporting
  processes"), Clause 11, covers confidence in the use of software tools.
- ISO 21448:2022, *Road vehicles — Safety of the intended functionality.*
- N. Kalra and S. M. Paddock, *Driving to Safety: How Many Miles of Driving
  Would It Take to Demonstrate Autonomous Vehicle Reliability?*, RAND
  Corporation, RR-1478-RC, 2016.
- E. B. Wilson, "Probable inference, the law of succession, and statistical
  inference", *Journal of the American Statistical Association*, 22:209–212,
  1927.
- J. L. Fleiss, "Measuring nominal scale agreement among many raters",
  *Psychological Bulletin*, 76(5):378–382, 1971.
- J. Cohen, "A coefficient of agreement for nominal scales", *Educational and
  Psychological Measurement*, 20(1):37–46, 1960.
- J. R. Landis and G. G. Koch, "The measurement of observer agreement for
  categorical data", *Biometrics*, 33(1):159–174, 1977.

**A note on citation precision.** Standards are cited above only for what I am
confident they contain. Clause numbering refers to the 2018 second edition of
ISO 26262; readers should check against their own copy, and the argument in
this README does not depend on the numbering being exact — only on the
substance of what tool qualification produces. If I have mischaracterised the
content of any standard cited here, that is a defect in this README and I would
like an issue raised against it.

---

## Contributing

Issues and pull requests welcome. The two most useful things anyone could send:

1. **Prior art that collapses the gap argument.** If a standard or published
   method already does this, I want to cite it.
2. **A correction to the statistics.** The tests are written to be readable and
   checkable for exactly this reason. If a variance component, an interval or a
   kappa is wrong, a failing test is the clearest way to say so.

---

## Author and licence

Linlin Wang.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
