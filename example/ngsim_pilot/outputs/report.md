# NGSIM US-101 Public-Data Replay Pilot

**Report status:** reproducible method-demonstration pilot; not an industrial HIL/SIL bench qualification and not independent third-party validation.  
**Generated:** 2026-08-16T07:46:02.904211+00:00  
**Protocol implementation:** `msa-ad` 0.2.0 at commit `b244e87d416b14f1779b408d67512854575a8e87`

## Executive finding

This pilot demonstrates that the `msa-ad` workflow can ingest a fixed slice of real U.S. road-traffic measurements, produce a balanced crossed replay study, compare replay configurations to a declared reference channel, and measure known-fault detection with traceable inputs and outputs. It does **not** prove that a production automated-driving HIL bench is accurate, because the three “benches” here are software measurement configurations applied to one public source dataset.

The crossed study used 30 real following-event windows × 3 configurations × 3 sampling-phase replicates = 270 measurements. The result was **acceptable** under the imported AIAG bands: %GRR = 6.36%, ndc = 22. This is a finding about the deliberately compared speed-estimation configurations and sampling phase, not a universal property of NGSIM or of any HIL facility.

The seeded-fault campaign executed 100 positive controls. It detected 100, for a measured rate of 100.0% with 95% Wilson CI [96.3%, 100.0%]. The clean-window screening evaluated 20 candidate windows while accumulating 20 eligible baselines; 0 triggered at least one predeclared integrity monitor and were excluded from the positive-control campaign. Exclusions remain visible in `baseline_monitor_results.csv`.

## Data provenance

- Publisher: U.S. Department of Transportation, Federal Highway Administration / ITS JPO.
- Dataset: Next Generation Simulation (NGSIM) Vehicle Trajectories and Supporting Data.
- Site: US-101, Los Angeles, California.
- Source window: Unix milliseconds 1118847200000 through 1118847260000, inclusive (60 seconds).
- Source rows: 75,110; unique vehicles: 277; unique timestamps: 601.
- Source query: `https://data.transportation.gov/resource/8ect-6jqj.csv?%24select=vehicle_id%2Cframe_id%2Ctotal_frames%2Cglobal_time%2Clocal_x%2Clocal_y%2Cglobal_x%2Cglobal_y%2Cv_length%2Cv_width%2Cv_class%2Cv_vel%2Cv_acc%2Clane_id%2Cpreceding%2Cfollowing%2Cspace_headway%2Ctime_headway%2Clocation&%24where=location%3D%27us-101%27%20and%20global_time%20between%201118847200000%20and%201118847260000&%24order=global_time%2Cvehicle_id&%24limit=100000`
- Raw CSV SHA-256: `c24113dc44c0b2e5af4aad99f13a647a05dbba7d84a3ce1ac19d6154eebfc981`
- License recorded by the U.S. DOT portal: CC BY-SA 4.0.
- Dataset DOI: https://doi.org/10.21949/1504477

No personally identifying fields are present in the extracted table; `vehicle_id` is a dataset-local trajectory identifier. This report uses “public real data,” not “de-identified proprietary bench data.”

## Study design

### Continuous metric

Each scenario is an 8.0-second real following-event window at the source 10 Hz cadence. The continuous response is the fifth percentile of a transparent **two-second residual-clearance surrogate**:

`(front-to-front space headway − leader length) − 2.0 × max(follower speed − leader speed, 0)`

The unit is feet; lower is worse. This is an engineering demonstration metric, not a statutory TTC definition. A binary demonstration verdict uses zero feet as the threshold.

### Configurations and replicates

| bench/configuration | speed channel |
|---|---|
| DOT_published_speed | NGSIM `v_vel` |
| local_position_SG | Savitzky–Golay derivative of `local_y` |
| global_position_SG | magnitude of Savitzky–Golay derivatives of `global_x`, `global_y` |

Each configuration is evaluated on sampling phases 0, 1, and 2 modulo 3. These are **sampling-phase sensitivity repeats**, not repeated hardware executions. Therefore the study is suitable to demonstrate the crossed analysis and expose configuration sensitivity; it is not evidence of scheduler or hardware repeatability.

The declared reference for bias analysis is the full-rate, source-published `v_vel` calculation on the same window. It is a traceable anchor channel, not an independently calibrated physical master.

## Results

### Gage R&R summary

- %GRR: **6.36%** (acceptable)
- EV (sampling-phase repeatability SD): 2.5305 ft
- AV (configuration reproducibility SD): 0.0662 ft
- PV (scenario variation SD): 39.7251 ft
- ndc: **22**
- Scenario × configuration interaction pooled: True (p = 1, alpha = 0.25)

| bench | mean | bias_vs_grand_mean | repeatability_sd | df | sd_ratio_vs_best |
| --- | --- | --- | --- | --- | --- |
| DOT_published_speed | 74.2833 | -0.3135 | 2.7672 | 60 | 1.0000 |
| global_position_SG | 74.7962 | 0.1994 | 2.9018 | 60 | 1.0487 |
| local_position_SG | 74.7110 | 0.1141 | 2.9456 | 60 | 1.0645 |

### Binary agreement

- Majority between-configuration agreement: 30/30 = 100.0%, 95% Wilson CI [88.6%, 100.0%].
- Fleiss kappa over all trials: nan.
- Disagreement scenarios: 0.

All 270 replay results fell on the “pass” side of the zero-foot demonstration threshold. Accordingly, the 100% raw agreement is **non-discriminating** and kappa is undefined; it must not be cited as evidence that the configurations distinguish pass from fail. A later confirmatory study needs pre-registered scenarios on both sides of a safety-derived threshold.

### Bias and linearity against the declared anchor

| configuration | n | mean_bias_ft | bias_95ci_low | bias_95ci_high | linearity_slope | linearity_p |
| --- | --- | --- | --- | --- | --- | --- |
| DOT_published_speed | 90 | 0.4253 | -0.2001 | 1.0508 | -0.0086 | 0.2868 |
| global_position_SG | 90 | 0.9382 | 0.2814 | 1.5951 | -0.0119 | 0.1563 |
| local_position_SG | 90 | 0.8530 | 0.2269 | 1.4791 | -0.0099 | 0.2180 |

### Seeded known-fault controls

Predeclared controls and monitors:

| fault class | injection | expected monitor |
|---|---|---|
| CLOCK_STEP | +300 ms time step | cadence gap >150 ms |
| SPEED_BIAS | +10 ft/s persistent bias | median speed-channel disagreement >6 ft/s |
| POSITION_STEP | +12 ft longitudinal step | one-step kinematic innovation >6 ft |
| SPEED_FREEZE | 2.0 s held speed | ≥15 near-identical frames while position advances >20 ft |
| LEAD_SIGNAL_LOSS | 1.0 s interior loss | bracketed loss of lead/headway for ≥5 frames |

| hazard_class | seeded | detected | escaped | detection_rate | ci_low | ci_high | below_threshold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CLOCK_STEP | 20 | 20 | 0 | 1.0000 | 0.8389 | 1.0000 | False |
| LEAD_SIGNAL_LOSS | 20 | 20 | 0 | 1.0000 | 0.8389 | 1.0000 | False |
| POSITION_STEP | 20 | 20 | 0 | 1.0000 | 0.8389 | 1.0000 | False |
| SPEED_BIAS | 20 | 20 | 0 | 1.0000 | 0.8389 | 1.0000 | False |
| SPEED_FREEZE | 20 | 20 | 0 | 1.0000 | 0.8389 | 1.0000 | False |

The detection rule for each positive control was fixed by `expected_monitor` before the campaign outcome was calculated. A hit from an unrelated monitor is logged but does not count as detection of that control.

These controls are deliberately conspicuous integrity failures. A 100% result here is a smoke-test result, not a detection-limit study. A confirmatory campaign should use a pre-registered magnitude sweep, including sub-threshold and near-threshold injections, and report both clean-run false alarms and seeded-fault misses.

## Reproducibility package

The following files are the audit trail:

- `data/ngsim_us101_60s.csv`: unmodified API extract.
- `outputs/bench_runs.csv`: exact long-form Gage R&R and attribute-agreement input.
- `outputs/fault_catalogue.csv`: positive-control definitions.
- `outputs/campaign_results.csv`: one result per seeded fault, including all triggered monitors.
- `outputs/baseline_monitor_results.csv`: unseeded monitor outcomes and visible exclusions.
- `outputs/selected_scenarios.csv`: scenario identifiers and source time windows.
- `outputs/manifest.json`: source URL, hashes, package versions, and analysis parameters.
- `outputs/full_statistical_output.txt`: verbatim text produced by `msa-ad` renderers.

Re-run from this directory with:

```bash
cd example/ngsim_pilot
python run_pilot.py
```

(from a checkout of the `msa-ad` repository, with `numpy`, `scipy` and
`pandas` installed)

The script reuses the cached raw extract. Deleting the cached CSV forces a fresh download from the exact Socrata query; compare its SHA-256 with the manifest before treating a later run as identical.

## Limitations and claim boundary

1. The source is real traffic data, but no production ADS software, simulator, HIL rig, or fault-injection bench was exercised.
2. The three configurations share the same originating video-derived trajectory data and therefore are not independent facilities.
3. Sampling phase is not the same as repeated execution of a deterministic bench. A true bench pilot must repeat identical inputs on separate bench hosts or rigs and record scheduler, real-time bus, firmware, compiler, model, and hardware versions.
4. The bias anchor is the dataset's own published velocity channel, not a separately calibrated master. It can reveal disagreement among derived channels but cannot establish absolute truth.
5. Seeded faults test the five declared data-integrity monitors only. They do not establish scenario/hazard coverage of an ADS safety campaign.
6. Selection requires complete 8-second following windows and, for positive controls, a clean baseline. The resulting sample is not a random sample of the US-101 dataset or an ODD.
7. AIAG thresholds are used as a transferred decision convention. Their applicability to this surrogate metric is part of the proposed method and has not been standardized.

## Appropriate use in an NIW filing

The defensible description is: **“a reproducible pilot applying the proposed protocol to publicly available real-road trajectory measurements.”** Do not describe it as customer adoption, independent facility validation, production HIL qualification, or evidence that `msa-ad` has been accepted by an OEM. The next evidentiary step is an externally witnessed replay on at least two independently configured SIL/HIL benches using an identical scenario bundle and pre-registered thresholds.
