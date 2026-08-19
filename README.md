# msa-ad

**Measurement System Analysis for Automated-Driving Validation.**

Gage R&R, attribute agreement, and seeded-fault coverage verification for
simulation, hardware-in-the-loop (HIL) and fault-injection benches.

It quantifies the repeatability, reproducibility, reference-relative bias and
monitor effectiveness of a bench. It is evidence that supports a tool-validation
argument; it does not, on its own, establish that a simulation is accurate or
valid for a given operational design domain — that is a separate obligation
requiring an independent physical reference. See
[Where this sits in UL 4600](#where-this-sits-in-ul-4600).

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
| trial/replicate | repeated execution of the same scenario              |
| measurement     | safety-margin metric, or pass/fail verdict           |

The replicate row is where the transfer stops being mechanical. On a bench,
repeated execution usually means a new random seed, and the seed drives
*deliberately injected* stochasticity — traffic-agent behaviour, sensor-noise
models. That scatter is aleatory variation of the scenario, not error of the
apparatus, and charging it to repeatability produces a `%GRR` that describes
the stochastic model rather than the rig. The **two-tier design** replicates
twice, once with the seed held fixed and once with it varied, and reports the
two characterisations side by side rather than as one confounded figure.

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
precision-versus-bias decomposition — in mandatory form.

**UN Regulation No. 157**, Annex 4 ¶4.2 separately requires that "manufacturers
shall demonstrate the scope of the simulation tool, its validity for the scenario
concerned as well as the validation performed for the simulation tool chain
(correlation of the outcome with physical tests)". The same paragraph, as amended
in 2023, adds that "simulation shall not be a substitute for physical tests in
Annex 5 and Annex 6 to this UN Regulation" — worth noting, because it shows a
regulator that requires toolchain validation and still declines to let simulation
stand alone. ¶4.2 cross-refers to **Schedule 8 of the 1958 Agreement**, "General
conditions for virtual testing methods", whose §2.2 provides that "the
mathematical model shall be validated in comparison with the actual test
conditions" and that "comparability of the test results shall be proven".

So the interesting question is not whether anyone has thought about this. They
have, and in more detail than the ISO functional-safety standards suggest.

### What those instruments leave open

**None of them defines the metric or the threshold.**

EU 2022/1426 §3.4.5.5.1 provides that *"the requirement for the correlation
threshold is defined during the M&S analysis"* — that is, by the manufacturer
whose toolchain is being assessed.

Schedule 8 of the 1958 Agreement is more striking still. It is roughly 350 words
in three short sections. It requires that "comparability of the test results shall
be proven", and then stops. It names no output quantity to be compared, specifies
no number of physical tests ("as appropriate"), states no degree of agreement, and
incorporates no external standard by reference — no ISO, no ASME V&V, nothing. The
words *tolerance*, *threshold*, *criterion*, *confidence level* and *error norm* do
not appear in it at all. The closest the chain comes to a check is R157 ¶4.2.1,
under which the approval authority *may* verify the accuracy of simulation tools
against track or road results — a discretionary power held by the authority, not a
criterion binding the manufacturer.

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
be quantified. **An MSA study may contribute quantitative evidence to a 1c
argument** — a number that can be trended and compared, rather than a verdict
that cannot — but it does not by itself discharge 1c: validation of a tool
against its use cases includes establishing that the tool produces correct
results, which is a separate obligation from characterising the dispersion of
what it produces. If you already run Clause 11 on your benches, this is meant to
slot into it, not to compete with it.

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

**What I am claiming:** that I am not aware of a published protocol applying the
production measurement-system-analysis method — a variance-component
decomposition into repeatability and reproducibility with named acceptance
bands, a linearity and stability study across the operating range, calibrated
seeded-fault positive controls, and reproducibility across independent
facilities under a common protocol — as an integrated qualification of an
automated-driving validation bench treated as a measurement instrument. And that
because no *regulation* defines the metric, the statistical technique or the
acceptance threshold, credibility evidence is not comparable between
organisations.

**Two corrections to earlier drafts, made after reading the sources below.**
First, the individual components are not all unprecedented: Riedmaier et al.
already inject known modelling errors to measure whether a validation decision
procedure detects them, and Chance et al. already characterise simulator
determinism empirically against a stated tolerance. The claim is about the
assembly and its object, not about the invention of the pieces. Second, "no
instrument anywhere states a threshold" would be false: JAMA's *Automated
Driving Safety Evaluation Framework* Ver 4.0 (March 2026) states numeric
acceptance criteria for sensor-model agreement. It is an industry-association
guideline with no legal force, written by the parties being assessed, in one
national market, referenced normatively by no regulator — which is the
comparability problem illustrated rather than refuted, but the word "none"
should not be used unqualified.

"I have not found it" remains a weak form of argument and the surrounding space
is large. Ground I am aware of, and which anyone evaluating this should check:

- **Commission Implementing Regulation (EU) 2022/1426**, Annex III Part 4 —
  the most directly on-point instrument I know of;
- **UN-R157** Annex 4 ¶4.2 (consolidated text: E/ECE/TRANS/505/Rev.3/Add.156/Rev.1,
  27 March 2025; authentic text ECE/TRANS/WP.29/2022/59/Rev.1) and **Schedule 8 of
  the 1958 Agreement Rev.3**, "General conditions for virtual testing methods"
  (authentic text ECE/TRANS/WP.29/2016/2, §2.2) — Schedule 8 has never been amended;
- **UNECE NATM** (New Assessment/Test Method) master document — and note its
  history: ECE/TRANS/WP.29/2022/57, Annex III Appendix 2, "Example of correlation
  methodologies", named eight measures with formulae (relative error criterion,
  RMSE, L-infinity, Sprague-Geers, Pearson, t-test, ANOVA, Kolmogorov-Smirnov);
  the 2024 successor ECE/TRANS/WP.29/2024/39 removed that appendix while keeping
  the instruction to use "the correlation methodologies"; and UN Regulation No.
  171 (E/ECE/TRANS/505/Rev.3/Add.170) inherits the instruction as "as defined in
  Annex II", where R171's annexes run 1 to 5 and there is no Annex II;
- **Chance, Ghobrial, McAreavey, Lemaignan, Pipe, Eder**, "On Determinism of Game
  Engines used for Simulation-based Autonomous Vehicle Verification",
  *IEEE T-ITS* (2022), arXiv:2104.06262 — **the closest published apparatus
  characterisation, and the only one reproducible by an outsider.** 1000 repeated
  runs per configuration, actor-path position as the measurand, maximum deviation
  from the mean against an a priori 1 cm tolerance, with CPU/GPU utilisation as
  the independent variable; determinism holds below roughly 75% utilisation. It
  imports precision and tolerance vocabulary from mechanical engineering
  explicitly. What it does not do: variance components, an operator or
  reproducibility factor, bias or linearity, attribute agreement, seeded-fault
  detector controls, or an acceptance framework beyond one chosen tolerance;
- the interlaboratory tradition in automotive bench testing, which is the
  precedent this package transposes: the WLTP brake-cycle study across eight
  laboratories analysed per ISO 5725-2/-5 with Mandel's h and k statistics,
  decomposing repeatability, sample effect, laboratory effect and total
  reproducibility (*Atmosphere* 11(12):1309, 2020, with Ford, Audi, GM, Brembo,
  TMD Friction and Link Engineering among the authors), and SAE 2010-01-1697 on
  brake-dynamometer variability, which separates variability caused by test parts
  from variability caused by the test setup. The method is standard practice on
  physical automotive benches and has not been pointed at simulation benches;
- ISO 26262 (functional safety), ISO 21448 (SOTIF), and ISO 34502 Annex F,
  "Qualification of virtual test platforms" — which is informative rather than
  normative, and I have not read its body text;
- **UL 4600** (17 March 2023), whose tool-qualification chapter requires that
  hazards and limitations associated with the use of simulations be identified,
  and whose safety-argument chapter names arguing from unvalidated simulation
  as a pitfall — read via UL's free digital view and mapped against this
  package in the section below;
- NASA-STD-7009 on models-and-simulations credibility, and the ASME V&V series
  on verification and validation in computational modelling, including V&V 40's
  risk-informed credibility framework;
- **GB/T 47025-2026** (China, in force 28 January 2026), whose **Appendix A is normative** and
  titled "Assessment of simulation test credibility". Read in full from the Chinese government's
  free standards portal: it requires that a correlation threshold be established (A.3.5), that
  validation results meet it (A.5.3.2), and that the model's validation *method and threshold* be
  recorded (A.2.2.2) — i.e. it treats both as applicant inputs and names no metric, no statistical
  technique and no number. The mandatory **GB 47955-2026** carries a near-verbatim clone of the
  same appendix. Also **GB/T 44721-2024**, whose simulation reference (clause 4.21) is conditional
  and generic;
- **ASAM's "Quantifying Simulation Quality" project** (P_2025_04), running since
  December 2025, whose stated premise is that no standardised metrics currently
  exist for assessing simulation quality — if that project publishes something
  that does what is described here, this package should defer to it;
- **Riedmaier, Schneider, Danquah, Schick, Diermeyer**, "Non-deterministic model
  validation methodology for simulation-based safety assessment of automated
  vehicles", *Simulation Modelling Practice and Theory* 109:102274 (2021), and
  Riedmaier's TUM dissertation (mediaTUM 1615375, open access), which contains
  it. **This is the closest prior art to the seeded-fault component, and it
  anticipates part of it.** Using the Method of Manufactured Universes, they
  intentionally inject modelling errors of known magnitude and score whether
  their VV&UQ decision procedure detects them, evaluated with a binary
  classifier reporting precision and recall. Their own summary: "The validation
  methodology is itself validated by intentionally injecting modeling errors to
  determine if it can identify and correct them." What remains different here is
  the object being graded — they grade the *decision rule*, this package grades
  the *bench and its monitors* — and the design: theirs is a single fault of one
  magnitude in one direction, deliberately without measurement noise, reported as
  point estimates with no confidence interval, with no claimed coverage figure to
  compare against and no acceptance band. Those are differences of scope, not of
  kind, and anyone assessing novelty here should read their work first;
- the software-engineering mutation-testing literature, the nearest analogue in
  that field to the seeded-fault component. Note that mutation testing grades a
  *test suite*, not the apparatus or its oracle; Shin et al., "Towards
  Safety-Aware Mutation Testing for Autonomous Driving Systems"
  (arXiv:2606.26456, June 2026), is a vision paper whose §IV-E states this
  package's own problem as an open challenge — repeated simulator iterations
  assessed with statistically rigorous confidence intervals.

If any of these — or anything else — already prescribes a variance-decomposed
repeatability and reproducibility characterisation of a validation bench with
defined acceptance criteria, **please open an issue**. I would much rather cite
prior art than duplicate it, and a pointer that collapses this argument is more
useful to me than agreement with it. That has already happened once: EU 2022/1426
is in this list because looking for the counter-argument found it.

---

## Where this sits in UL 4600

UL 4600 (Standard for Safety for the Evaluation of Autonomous Products) makes
simulation a first-class safety-case concern: its tool-qualification chapter
requires that hazards and limitations associated with the use of simulations
be identified — from physics-modelling accuracy and the handling of simulated
time, through result reporting and the performance of simulation monitoring
functions, to experimental coverage and the statistical analysis of results —
and checks conformance by inspecting tool-qualification evidence. What the
standard deliberately does not do is prescribe a measurement method, a metric,
or an acceptance band for producing that evidence.

msa-ad is one candidate for that missing layer. Clause 13.3.2 of the standard
(UL 4600, 17 March 2023) requires that hazards and limitations associated with
the use of simulations be identified, and its REQUIRED list at 13.3.2.2 names
the topics a safety case has to address. Each msa-ad study answers one of them
with a number rather than an assertion:

| msa-ad study | UL 4600 13.3.2.2 topic it evidences |
|---|---|
| Bias / linearity vs. a declared reference | (c)(2) physics simulation accuracy — **only to the extent the reference is independent.** Against an independently calibrated physical reference this is accuracy evidence; against an anchor channel drawn from the same source (as in the pilot below) it is evidence of channel disagreement and nothing more |
| Cadence / clock monitors, `CLOCK_STEP`-class seeded faults | (c)(3) representation and management of simulated time |
| Seeded known-fault campaign | (c)(4) simulation result reporting, including failure reporting; (c)(5) performance of simulation monitoring functions |
| Coverage-validity ratio with Wilson intervals | (b)(3) inclusion of low-probability safety-related workload elements — the coverage a seeded control can falsify |
| Two-tier replicate design | (b)(2) real-time execution considerations — the standard's own examples are simulated-sensor-input timing, task scheduling jitter, and loop-closure timing |

Clause 13.2.1 is the companion: the safety case must identify the tools used
across the lifecycle — simulation among them — with vendor, version, and a
description of use. Identification is where a tool becomes an object of
evidence; measurement is what msa-ad adds on top of it.

The standard also names, at 5.3.3.2(j), the failure mode this package exists
to make measurable: arguing low risk from unvalidated simulation results alone
is prone to missing risks introduced by simulation defects, modelling faults,
and the simplifications made in building the abstraction. Validating the
simulation is a proof obligation of its own, separate from whatever the
simulation is used to prove.

**What this package does not do, stated at the same volume as what it does.**
Establishing that a simulation is accurate enough for its intended use is a
proof obligation in its own right, and it is not the obligation msa-ad
discharges. Repeatability, reproducibility, and monitor effectiveness are
properties of the instrument, not of its correctness: a bench can reproduce the
same wrong answer indefinitely and score well on every study in this package.
Accuracy validation requires a stated intended use, an independent physical
reference, acceptance bounds fixed before results are seen, and separated
calibration and validation data — none of which follows from a %GRR figure.
The right way to read these studies is as evidence *supporting* a tool-validation
argument, never as a substitute for the accuracy leg of it.

Two discipline notes. First, these outputs are offered as *candidate
tool-qualification evidence* for the inspection the standard describes —
nothing here is, or should ever be described as, "UL 4600 compliant."
Second, the standard's warning that machine-learning systems can exploit
rendering artifacts in simulation describes a fault class this package does
not yet implement: seeded rendering-artifact faults for perception benches
are a natural future addition to the catalogue, and are listed here so the
absence is a stated limitation rather than an oversight.

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
    gage_rr_anova, two_tier_gage_rr, attribute_agreement,
    analyse_seeded_faults, compare_claimed_coverage,
    render_gage_rr_report, render_two_tier_report, render_seeded_fault_report,
)

runs = pd.read_csv("example/bench_runs.csv")

# Continuous safety-margin metric -> crossed ANOVA Gage R&R
grr = gage_rr_anova(runs, scenario_col="scenario_id",
                    bench_col="bench_id", value_col="min_ttc_s")
print(render_gage_rr_report(grr))
print(grr.pct_grr, grr.ndc, grr.verdict)

# Replicates split into fixed-seed and varied-seed tiers -> two-tier study
two_tier = two_tier_gage_rr(
    pd.read_csv("example/bench_runs_two_tier.csv"),
    value_col="min_ttc_s", tier_col="tier",
    deterministic_benches=["HIL-A", "HIL-B"],
)
print(render_two_tier_report(two_tier))
print(two_tier.fixed_seed.pct_grr,       # the instrument
      two_tier.varied_seed.pct_grr,      # the stochastic model
      two_tier.var_aleatory, two_tier.aleatory_clamped,
      two_tier.determinism_verdict)

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
`BinaryDataError` rather than returning a meaningless `%GRR`. Passing only one
tier to `two_tier_gage_rr` raises `MissingTierError` rather than quietly
reporting a confounded figure as if it were an instrument characterisation.
Both guards are deliberate features; see "Statistical notes" below.

---

## Worked example

**All data in this example is synthetic.** It is generated by `msa_ad.datagen`
from a fixed seed and is not measured data from any bench, programme or
vehicle. It is constructed to contain findings, because a demonstration in
which everything passes demonstrates nothing: one bench (`HIL-C`) has roughly
four times the repeatability standard deviation of the others, several
scenarios sit near the pass/fail threshold, one hazard class detects poorly,
and one bench documented as reproducing a fixed seed exactly does not.

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

### 1c. Two-tier study — apparatus error versus injected scenario noise

Every scenario re-executed twice over on the same three benches: three
fixed-seed replicates (Tier A) and five varied-seed replicates (Tier B).
`HIL-A` and `HIL-B` are documented as reproducing a fixed seed exactly.

```
==============================================================================
BENCH CHARACTERISATION - TWO-TIER GAGE R&R (crossed ANOVA)
==============================================================================
Metric              : min_ttc_s
Tier A, fixed seed  : 15 scenarios x 3 benches x 3 replicates = 135 executions
Tier B, varied seed : 15 scenarios x 3 benches x 5 replicates = 225 executions
Tier column         : tier   (A = 'fixed_seed', B = 'varied_seed')

DETERMINISM AUDIT  (Tier A - seed held fixed)
------------------------------------------------------------------------------
bench           declared  fixed-seed SD  widest spread  worst scenario   verdict
HIL-A                yes       0.000000       0.000000  CUT_IN_100KPH         OK
HIL-B                yes       0.012585       0.040143  DEBRIS_AVOIDANCE VIOLATED
HIL-C                  -       0.080494       0.277432  CUT_IN_60KPH
------------------------------------------------------------------------------
  Declared deterministic: HIL-A, HIL-B. DETERMINISM VIOLATED by HIL-B (SD =
  0.012585, widest fixed-seed spread 0.040143 on DEBRIS_AVOIDANCE). [...]

SIDE BY SIDE  (each tier analysed independently)
------------------------------------------------------------------------------
quantity                            Tier A (fixed seed)  Tier B (varied seed)
Repeatability EV                               0.047038              0.234585
Reproducibility AV                             0.122154              0.106799
Gage R&R                                       0.130898              0.257752
Scenario variation PV                          0.697930              0.698791
Total variation TV                             0.710099              0.744812
%GRR                                             18.43%                34.61%
ndc                                                   7                     3
AIAG verdict                                   marginal          unacceptable
replicates per cell                                   3                     5
interaction                                    retained                pooled

ALEATORY SCENARIO VARIANCE  (Tier B minus Tier A)
------------------------------------------------------------------------------
  apparatus (Tier A repeatability variance) :      0.002213
  Tier B replicate variance                 :      0.055030
  difference                                :      0.052818
  aleatory scenario variance                :      0.052818   (SD 0.229821)
  share of Tier B replicate variance        :         95.98%
  F = var_B / var_A = 24.8718 on (208, 90) df, p = 0.0000
  -> Tier B scatter exceeds Tier A significantly (alpha = 0.05)

PER-BENCH SPLIT
------------------------------------------------------------------------------
bench            apparatus var    Tier B var   aleatory var   aleatory SD clamped
HIL-A                 0.000000      0.052349       0.052349      0.228800       -
HIL-B                 0.000158      0.047428       0.047269      0.217415       -
HIL-C                 0.006479      0.067790       0.061311      0.247610       -
```

Two findings, and they point in opposite directions.

The first is a correction. A single-tier study on the varied-seed data alone
reports `%GRR = 34.6%` and `ndc = 3` — an unacceptable measurement system. But
96% of that replicate variance disappears once the seed is held fixed: it was
the injected scenario stochasticity, recovered here at an SD of 0.230 s against
the 0.220 s the generator put in. The instrument itself sits at `%GRR = 18.4%`
with `ndc = 7`, which is marginal rather than unacceptable. Those are different
verdicts about different things, and the single-tier number was reporting the
traffic model.

The second is a defect. `HIL-B` is documented as reproducing a fixed seed
exactly and does not: re-executing `DEBRIS_AVOIDANCE` with the seed pinned
moved the answer by 0.040 s. That is not a small `%GRR` contribution to be
noted and moved past. A bench that cannot reproduce its own fixed-seed run
cannot support a seed-controlled regression comparison at all, which is what
most release gating on a simulation bench actually rests on. The audit reports
it as a verdict for that reason, rather than folding it into a variance term
where it would disappear.

Note the per-bench split: the three aleatory estimates (0.229, 0.217, 0.248)
agree with each other, as they should — the injected stochasticity is a
property of the scenario, not of the bench that ran it. A bench disagreeing
with the others there would be evidence that the seed does not control the same
models everywhere.

### 1d. The tier guard

```
MissingTierError raised, as it should be:

    the fixed-seed tier ('fixed_seed') is absent.

    Without fixed-seed replicates there is nothing to subtract, and
    the varied-seed repeatability term is an upper bound on the
    apparatus error rather than an estimate of it: it also contains
    every bit of deliberately injected scenario stochasticity.
    Re-execute a subset of scenarios with the seed held fixed, or run
    msa_ad.gage_rr.gage_rr_anova() on the tier you have and report the
    result as what it is - a confounded figure.
```

### 1e. Bench characterisation — binary verdicts

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
* Two-tier split: the apparatus accounts for 4.0% of the varied-seed replicate variance;
  the other 96.0% is injected scenario stochasticity (SD 0.230 s). A single-tier study
  charges all of it to repeatability: %GRR 18.4% (Tier A) vs 34.6% (Tier B).
* Determinism audit FAILED for ['HIL-B']: declared to reproduce a fixed seed
  exactly, and did not.
* Attribute agreement: between-bench strict reproducibility = 0.533, Fleiss' kappa = 0.580.
* Coverage-validity ratio: 99/120 = 0.825 [0.747, 0.883].
* Hazard classes flagged at threshold 0.80: ['perception_false_negative', 'planning_timing'].
* Claimed coverage 0.95 vs measured 0.825: discrepancy +0.125, claim outside the 95% interval.
* 5 catalogued fault(s) were never executed and are excluded from the ratio.
```

---

## Real-data pilot: NGSIM US-101 replay

`example/ngsim_pilot/` applies the full workflow to a fixed 60-second slice of
the U.S. DOT/FHWA NGSIM US-101 vehicle-trajectory dataset (DOI
[10.21949/1504477](https://doi.org/10.21949/1504477)): a balanced crossed
Gage R&R over 30 real following-event windows x 3 speed-estimation
configurations x 3 sampling-phase replicates, bias and linearity against a
declared anchor channel, and a pre-registered seeded known-fault campaign of
100 positive controls. Every input, output, hash and parameter is recorded in
`example/ngsim_pilot/outputs/`, and `outputs/report.md` states the claim
boundary explicitly: this is a reproducible method demonstration on public
real-road measurements, not an industrial HIL/SIL bench qualification and not
third-party validation.

### What the pilot's fault catalogue does and does not cover

A fault catalogue is itself a coverage claim, so it gets a coverage
statement. Against the topics listed at 13.3.2.2, the pilot's five fault
classes (`CLOCK_STEP`, `SPEED_BIAS`, `POSITION_STEP`, `SPEED_FREEZE`,
`LEAD_SIGNAL_LOSS`) exercise the workload-data hazards at (d) — incorrect,
corrupted, and missing data — and the simulated-time hazard at (c)(3). They
do not exercise model translation into simulation objects, (c)(1), or
physics simulation accuracy, (c)(2): those are properties a bias study
against a reference must establish, not properties a data-integrity
injection can reach. Nor do they include rendering-artifact faults for
perception stacks, which the pilot does not run. A catalogue that stated
only what it covers would be making the exact mistake this package exists
to detect.

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

### Two-tier replicates: the apparatus versus the stochastic model

A crossed Gage R&R treats every repeated execution as a replicate and calls
whatever varies between them repeatability. On a simulation bench that reading
is usually false. Replicates are normally produced by changing the random seed,
and the seed is what drives the traffic-agent behaviour models, the sensor-noise
models and the actuator-latency draws. Those were put there on purpose. Their
scatter is aleatory variation *of the scenario*, and it belongs in a
scenario-sampling argument, not in an instrument-error term. A study that
conflates the two reports an `EV`, and therefore a `%GRR`, that mostly
describes the stochastic model.

`two_tier_gage_rr` replicates twice:

| tier                            | seed         | its replicate variance contains       |
| ------------------------------- | ------------ | ------------------------------------- |
| **A** — `TIER_FIXED_SEED`       | held fixed   | apparatus only                        |
| **B** — `TIER_VARIED_SEED`      | varied       | apparatus + injected scenario noise   |

This is the same distinction EU 2022/1426 §3.2.6.4 and §3.4.5.9.5 already ask
for, quoted earlier: stochastic models characterised *in terms of their
variance*, with *deterministic re-execution* possible, and the *aleatory*
component of uncertainty distinguished from the epistemic. Those paragraphs say
to separate the two and do not say how. Tier A and Tier B are one concrete way
to do it with a design a metrologist would recognise. I make no claim that it is
the way the regulation intends, only that it produces the two quantities the
regulation asks to see separated.

The existing crossed ANOVA is run on each tier independently — the same code,
under the same pooling rule — and the two results are reported side by side.
Tier A is the **instrument characterisation**: its `%GRR`, `ndc` and per-bench
terms are the ones that answer how much of a verdict came from the rig. Tier B
is the **stochastic-model characterisation** over the same scenarios. They are
not averaged into a single figure, because they are measurements of different
things.

The aleatory scenario variance follows by subtraction:

```
var_aleatory = var_repeatability(Tier B) − var_repeatability(Tier A)
```

unbiased under the design's own assumption — that the tiers differ only in
whether the seed moves, so the apparatus term is common to both. Being a
difference of two estimates it can come out negative when the true aleatory
variance is small against sampling error. It is then clamped to zero **and
flagged** (`aleatory_clamped`), because a silent clamp would upgrade "these
tiers are indistinguishable" into "there is no scenario stochasticity", which
is a much stronger claim and often the signature of a seed that is not reaching
the stochastic models at all. A one-sided F-test on the ratio of the two
repeatability terms is reported alongside, so a clamped estimate can be read
together with the evidence for any difference existing.

#### The determinism audit

Tier A also settles a question that a variance term is the wrong shape for. If
a bench documents deterministic re-execution — the same scenario, the same
seed, the same answer — then its expected Tier-A variance is not "small", it is
**exactly zero**. Any nonzero value contradicts the documentation.

`deterministic_benches=[...]` declares which benches make that claim, and each
one is audited against the **widest fixed-seed spread**: the largest max-minus-
min across the replicates of a single cell. The statistic is a range rather
than a deviation from the cell mean because the range of identical numbers is
exactly zero, whereas their distance from a computed mean is not — auditing a
zero-tolerance claim with a statistic carrying its own floating-point error
would manufacture violations. `determinism_tolerance` exists for a known
non-associative reduction in a logging path, defaults to `0.0`, and is printed
in the report whatever it is set to.

The result is a verdict (`upheld` / `violated` / `not_declared`), not a number
folded into `%GRR`. A bench that cannot reproduce its own fixed-seed run cannot
support a seed-controlled regression comparison, which is what release gating
on a simulation bench usually rests on; that consequence does not survive being
averaged into a variance component. Declaring nothing yields `not_declared`
and says so explicitly — an empty audit is not a pass.

Handled rather than assumed away:

- **Unequal replicate counts between tiers** are allowed. Each tier must be
  balanced in itself, which is what the ANOVA needs; both variance components
  stay unbiased and only their precision differs. `replicates_match` records
  it and the report says so. Fixed-seed re-execution is cheap and tells you
  little once the apparatus is quiet; the varied-seed tier is sampling a
  distribution and wants more draws.
- **A missing tier** raises `MissingTierError`, with a message stating what can
  still be computed. Without Tier A the varied-seed term is an upper bound on
  apparatus error, not an estimate of it. Without Tier B the apparatus
  characterisation is complete and the aleatory variance is simply not
  available.
- **Tiers covering different scenarios or different benches** raise
  `TierMismatchError`. `%GRR`, `ndc` and `PV` are all relative to the studied
  population, and subtracting a variance estimated over one from a variance
  estimated over another is not meaningful.
- **Binary input** raises `BinaryDataError`, checked across both tiers before
  either analysis is attempted, for exactly the reasons below.

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

`pytest` — 235 tests. The suite asserts the mathematics against independently
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
- **The two-tier split** is checked against a 2×2×2 design with a tier apiece,
  worked through by hand in `tests/test_two_tier.py`: Tier-A replicates at
  ±1 about their cell mean and Tier-B at ±3 give repeatability variances of
  1.6 and 14.4 and therefore an aleatory variance of exactly 12.8, with
  `F = 9.0` on (5, 5) degrees of freedom. Separately, synthetic tiers built
  with an apparatus SD and an aleatory SD combined in quadrature are asserted
  to recover both components within tolerance. A test also asserts that each
  tier's result equals `gage_rr_anova` run directly on that tier, so the
  two-tier path cannot drift into being a second implementation.
- **The determinism audit** is asserted to fire on nonzero fixed-seed spread,
  to stay silent for a bench nobody declared deterministic, to report
  `not_declared` rather than a pass when nothing is declared, and to respect an
  explicit tolerance in both directions.
- **The clamping flag** is asserted on tiers deliberately built the wrong way
  round, in the result object, in the verdict text and in the rendered report —
  a negative aleatory estimate must never be clampable in silence.
- **Guard tests** cover binary rejection in seven encodings, a missing tier in
  either direction, mismatched tier labels, and tiers covering different
  scenarios or benches; they assert the error messages explain *why* rather
  than only *that*.
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
- **Two-tier caveats.** The subtraction assumes the apparatus term is the same
  in both tiers — that the tiers differ only in whether the seed moves. A bench
  whose noise depends on the workload violates that, and nothing here detects
  it. No confidence interval is reported on the aleatory variance: it is a
  difference of two mean squares, and an exact interval for that is a
  Behrens–Fisher-shaped problem I have not attempted; the F-test on the ratio
  is offered instead. With `pool_interaction="auto"` the two tiers can reach
  different pooling decisions, which makes the two repeatability terms slightly
  different quantities; `pooling_matches` records it and the report says so,
  but the subtraction is still performed. The determinism audit is evidence
  only over the scenarios executed — it cannot establish determinism, only
  refute it.
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

## Citation

Machine-readable citation metadata lives in [`CITATION.cff`](CITATION.cff);
GitHub renders it as the "Cite this repository" button in the sidebar.

An archived, citable snapshot is deposited on Zenodo. Cite the **concept DOI**,
which always resolves to the latest archived version:

> Wang, L. *msa-ad: Measurement System Analysis for Automated-Driving
> Validation.* Zenodo. DOI: [`10.5281/zenodo.21963049`](https://doi.org/10.5281/zenodo.21963049)

If you need to pin the exact code you ran, cite the version DOI of that
specific release instead; every release has its own.

---

## Author and licence

Linlin Wang.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
