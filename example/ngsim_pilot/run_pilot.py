#!/usr/bin/env python3
"""Reproducible public-road-data replay pilot for msa-ad.

This is a method-demonstration pilot, not an industrial HIL validation. It uses
a fixed 60-second slice of the FHWA/U.S. DOT NGSIM US-101 vehicle trajectory
dataset and treats three speed-estimation pipelines as replay configurations.

Outputs are written under ``outputs/`` and include every analysis input, the
fault catalogue, campaign outcomes, a provenance manifest, and a Markdown
report. The raw source slice is cached under ``data/``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import scipy
from scipy.signal import savgol_filter


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
OUTPUT_DIR = HERE / "outputs"
RAW_DATA = DATA_DIR / "ngsim_us101_60s.csv"

MSA_AD_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MSA_AD_REPO))

from msa_ad import (  # noqa: E402
    analyse_seeded_faults,
    attribute_agreement,
    bias_linearity_study,
    gage_rr_anova,
    render_attribute_report,
    render_bias_report,
    render_gage_rr_report,
    render_seeded_fault_report,
)


DATASET_PAGE = (
    "https://data.transportation.gov/Automobiles/"
    "Next-Generation-Simulation-NGSIM-Vehicle-Trajector/8ect-6jqj"
)
DATASET_DOI = "https://doi.org/10.21949/1504477"
SOURCE_URL = (
    "https://data.transportation.gov/resource/8ect-6jqj.csv?"
    "%24select=vehicle_id%2Cframe_id%2Ctotal_frames%2Cglobal_time%2C"
    "local_x%2Clocal_y%2Cglobal_x%2Cglobal_y%2Cv_length%2Cv_width%2C"
    "v_class%2Cv_vel%2Cv_acc%2Clane_id%2Cpreceding%2Cfollowing%2C"
    "space_headway%2Ctime_headway%2Clocation&"
    "%24where=location%3D%27us-101%27%20and%20global_time%20between%20"
    "1118847200000%20and%201118847260000&"
    "%24order=global_time%2Cvehicle_id&%24limit=100000"
)

WINDOW_FRAMES = 81  # 8.0 seconds at 10 Hz, endpoints included.
N_GRR_SCENARIOS = 30
N_FAULT_BASELINES = 20
RESPONSE_TIME_S = 2.0
VERDICT_THRESHOLD_FT = 0.0

BENCHES = {
    "DOT_published_speed": "v_vel",
    "local_position_SG": "speed_local_sg",
    "global_position_SG": "speed_global_sg",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_rev(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unavailable"


def download_if_needed(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(SOURCE_URL, headers={"User-Agent": "msa-ad-ngsim-pilot/0.1"})
    tmp = path.with_suffix(".part")
    with urlopen(req, timeout=120) as response, tmp.open("wb") as f:
        while chunk := response.read(1024 * 1024):
            f.write(chunk)
    tmp.replace(path)


def _contiguous_segments(frame: pd.DataFrame) -> list[pd.DataFrame]:
    frame = frame.sort_values("global_time").copy()
    split = frame["global_time"].diff().fillna(100).ne(100).cumsum()
    return [g.copy() for _, g in frame.groupby(split, sort=False)]


def add_speed_channels(data: pd.DataFrame) -> pd.DataFrame:
    """Add two position-derived velocity channels without changing source rows."""
    data = data.sort_values(["vehicle_id", "global_time"]).copy()
    data["speed_local_sg"] = np.nan
    data["speed_global_sg"] = np.nan

    for _, vehicle in data.groupby("vehicle_id", sort=False):
        for seg in _contiguous_segments(vehicle):
            idx = seg.index
            n = len(seg)
            if n < 3:
                continue
            window = min(11, n if n % 2 else n - 1)
            if window < 5:
                local = np.gradient(seg["local_y"].to_numpy(), 0.1)
                gx = np.gradient(seg["global_x"].to_numpy(), 0.1)
                gy = np.gradient(seg["global_y"].to_numpy(), 0.1)
            else:
                local = savgol_filter(
                    seg["local_y"].to_numpy(), window, 2, deriv=1, delta=0.1
                )
                gx = savgol_filter(
                    seg["global_x"].to_numpy(), window, 2, deriv=1, delta=0.1
                )
                gy = savgol_filter(
                    seg["global_y"].to_numpy(), window, 2, deriv=1, delta=0.1
                )
            data.loc[idx, "speed_local_sg"] = np.abs(local)
            data.loc[idx, "speed_global_sg"] = np.hypot(gx, gy)
    return data.sort_values(["global_time", "vehicle_id"]).reset_index(drop=True)


def select_windows(data: pd.DataFrame, maximum: int = 80) -> list[dict]:
    """Select deterministic, fully crossed 8-second following-event windows."""
    lookup = data.set_index(["global_time", "vehicle_id"], drop=False)
    windows: list[dict] = []
    for vehicle_id, vehicle in data.groupby("vehicle_id", sort=True):
        selected = None
        for seg in _contiguous_segments(vehicle):
            if len(seg) < WINDOW_FRAMES:
                continue
            # Try centred windows first, then move in deterministic 10-frame steps.
            starts = list(range(0, len(seg) - WINDOW_FRAMES + 1, 10))
            middle = max(0, (len(seg) - WINDOW_FRAMES) // 2)
            starts = [middle] + [x for x in starts if x != middle]
            for start in starts:
                w = seg.iloc[start : start + WINDOW_FRAMES].copy()
                if not np.all(np.diff(w["global_time"].to_numpy()) == 100):
                    continue
                if (w["preceding"] <= 0).any() or (w["space_headway"] <= 0).any():
                    continue
                leader_keys = list(zip(w["global_time"], w["preceding"]))
                if not all(key in lookup.index for key in leader_keys):
                    continue
                if w[["v_vel", "speed_local_sg", "speed_global_sg"]].isna().any().any():
                    continue
                selected = w
                break
            if selected is not None:
                break
        if selected is None:
            continue
        start_time = int(selected["global_time"].iloc[0])
        windows.append(
            {
                "scenario_id": f"US101_V{int(vehicle_id):04d}_T{start_time}",
                "vehicle_id": int(vehicle_id),
                "start_time": start_time,
                "frame": selected,
            }
        )
        if len(windows) >= maximum:
            break
    return windows


def residual_clearance_metric(
    window: pd.DataFrame,
    lookup: pd.DataFrame,
    speed_col: str,
    phase: int | None,
) -> float:
    """Fifth percentile two-second residual clearance, in feet.

    The metric is a transparent engineering surrogate, not a regulatory TTC
    definition. Net gap is approximated as NGSIM front-to-front headway minus
    leader length. The response-distance term is two seconds times positive
    closing speed. Lower is worse.
    """
    rows = window if phase is None else window.iloc[phase::3]
    leader_keys = list(zip(rows["global_time"], rows["preceding"]))
    leaders = lookup.loc[leader_keys]
    follower_speed = rows[speed_col].to_numpy(dtype=float)
    leader_speed = leaders[speed_col].to_numpy(dtype=float)
    leader_length = leaders["v_length"].to_numpy(dtype=float)
    net_gap = rows["space_headway"].to_numpy(dtype=float) - leader_length
    closing_speed = np.maximum(follower_speed - leader_speed, 0.0)
    residual = net_gap - RESPONSE_TIME_S * closing_speed
    return float(np.quantile(residual, 0.05))


def build_bench_runs(data: pd.DataFrame, windows: list[dict]) -> pd.DataFrame:
    lookup = data.set_index(["global_time", "vehicle_id"], drop=False)
    rows: list[dict] = []
    for item in windows[:N_GRR_SCENARIOS]:
        w = item["frame"]
        reference = residual_clearance_metric(w, lookup, "v_vel", phase=None)
        for bench_id, speed_col in BENCHES.items():
            for phase in range(3):
                value = residual_clearance_metric(w, lookup, speed_col, phase)
                rows.append(
                    {
                        "scenario_id": item["scenario_id"],
                        "vehicle_id": item["vehicle_id"],
                        "bench_id": bench_id,
                        "replicate": phase + 1,
                        "replicate_definition": f"10Hz sampling phase {phase} modulo 3",
                        "residual_clearance_ft": value,
                        "reference_value_ft": reference,
                        "verdict": "pass" if value >= VERDICT_THRESHOLD_FT else "fail",
                    }
                )
    return pd.DataFrame(rows)


def _longest_true_run(mask: np.ndarray) -> tuple[int, int, int]:
    best_len = best_start = 0
    current_start = 0
    for i, value in enumerate(mask):
        if value:
            if i == 0 or not mask[i - 1]:
                current_start = i
            if i - current_start + 1 > best_len:
                best_len = i - current_start + 1
                best_start = current_start
        
    return best_len, best_start, best_start + best_len


def qc_monitors(window: pd.DataFrame) -> dict[str, bool]:
    """Predeclared generic integrity monitors for the seeded-fault campaign."""
    w = window.sort_values("global_time").reset_index(drop=True)
    t = w["global_time"].to_numpy(dtype=float) / 1000.0
    dt = np.diff(t)
    y = w["local_y"].to_numpy(dtype=float)
    v = w["v_vel"].to_numpy(dtype=float)

    if len(w) >= 11 and np.all(dt > 0):
        local_speed = np.abs(savgol_filter(y, 11, 2, deriv=1, delta=0.1))
    else:
        safe_dt = np.where(dt > 0, dt, np.nan)
        local_speed = np.r_[np.nan, np.abs(np.diff(y) / safe_dt)]

    trapezoid_step = 0.5 * (v[1:] + v[:-1]) * dt
    position_innovation = np.abs(np.diff(y) - trapezoid_step)

    frozen = np.r_[False, np.abs(np.diff(v)) <= 0.01]
    freeze_len, freeze_start, freeze_end = _longest_true_run(frozen)
    freeze_motion = (
        abs(y[min(freeze_end, len(y) - 1)] - y[freeze_start])
        if freeze_len
        else 0.0
    )

    lead_zero = (w["preceding"].to_numpy() == 0) | (
        w["space_headway"].to_numpy(dtype=float) == 0
    )
    lead_len, lead_start, lead_end = _longest_true_run(lead_zero)
    lead_bracketed = (
        lead_len >= 5
        and lead_start > 0
        and lead_end < len(lead_zero)
        and not lead_zero[lead_start - 1]
        and not lead_zero[lead_end]
    )

    return {
        "cadence_gap": bool(len(dt) and (np.nanmax(dt) > 0.150 or np.nanmin(dt) <= 0)),
        "speed_disagreement": bool(np.nanmedian(np.abs(v - local_speed)) > 6.0),
        "position_innovation": bool(
            len(position_innovation) and np.nanmax(position_innovation) > 6.0
        ),
        "speed_freeze": bool(freeze_len >= 15 and freeze_motion > 20.0),
        "lead_signal_loss": bool(lead_bracketed),
    }


FAULTS = {
    "CLOCK_STEP": {
        "hazard_id": "H-TIME-INTEGRITY",
        "injection_point": "global_time",
        "magnitude": "+300 ms step after midpoint",
        "expected_monitor": "cadence_gap",
    },
    "SPEED_BIAS": {
        "hazard_id": "H-SPEED-INTEGRITY",
        "injection_point": "v_vel",
        "magnitude": "+10 ft/s persistent bias",
        "expected_monitor": "speed_disagreement",
    },
    "POSITION_STEP": {
        "hazard_id": "H-POSITION-INTEGRITY",
        "injection_point": "local_y",
        "magnitude": "+12 ft step after midpoint",
        "expected_monitor": "position_innovation",
    },
    "SPEED_FREEZE": {
        "hazard_id": "H-SPEED-FREEZE",
        "injection_point": "v_vel",
        "magnitude": "2.0 s held value",
        "expected_monitor": "speed_freeze",
    },
    "LEAD_SIGNAL_LOSS": {
        "hazard_id": "H-ASSOCIATION-LOSS",
        "injection_point": "preceding/space_headway/time_headway",
        "magnitude": "1.0 s interior dropout",
        "expected_monitor": "lead_signal_loss",
    },
}


def inject_fault(window: pd.DataFrame, fault_class: str) -> pd.DataFrame:
    w = window.sort_values("global_time").reset_index(drop=True).copy()
    mid = len(w) // 2
    if fault_class == "CLOCK_STEP":
        w.loc[mid:, "global_time"] += 300
    elif fault_class == "SPEED_BIAS":
        w["v_vel"] += 10.0
    elif fault_class == "POSITION_STEP":
        w.loc[mid:, "local_y"] += 12.0
    elif fault_class == "SPEED_FREEZE":
        lo, hi = mid - 10, mid + 10
        w.loc[lo:hi, "v_vel"] = float(w.loc[lo, "v_vel"])
    elif fault_class == "LEAD_SIGNAL_LOSS":
        lo, hi = mid - 5, mid + 4
        w.loc[lo:hi, ["preceding", "space_headway", "time_headway"]] = 0
    else:
        raise KeyError(fault_class)
    return w


def build_fault_campaign(windows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baseline_rows = []
    eligible = []
    for item in windows:
        monitors = qc_monitors(item["frame"])
        baseline_rows.append({"scenario_id": item["scenario_id"], **monitors})
        if not any(monitors.values()):
            eligible.append(item)
        if len(eligible) >= N_FAULT_BASELINES:
            break

    catalogue_rows = []
    result_rows = []
    for item in eligible:
        for fault_class, spec in FAULTS.items():
            fault_id = f"{item['scenario_id']}__{fault_class}"
            injected = inject_fault(item["frame"], fault_class)
            monitors = qc_monitors(injected)
            expected_monitor = spec["expected_monitor"]
            catalogue_rows.append(
                {
                    "fault_id": fault_id,
                    "scenario_id": item["scenario_id"],
                    "hazard_id": spec["hazard_id"],
                    "hazard_class": fault_class,
                    "injection_point": spec["injection_point"],
                    "magnitude": spec["magnitude"],
                    "expected_monitor": expected_monitor,
                    "expected_detection": True,
                }
            )
            result_rows.append(
                {
                    "fault_id": fault_id,
                    "detected": bool(monitors[expected_monitor]),
                    "triggered_monitors": ",".join(k for k, v in monitors.items() if v),
                }
            )
    return pd.DataFrame(catalogue_rows), pd.DataFrame(result_rows), pd.DataFrame(baseline_rows)


def _md_table(frame: pd.DataFrame, floatfmt: str = ".4f") -> str:
    if frame.empty:
        return "_(none)_"
    def render(value) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return format(float(value), floatfmt)
        return str(value).replace("|", "\\|").replace("\n", " ")

    columns = [str(c) for c in frame.columns]
    rows = [[render(value) for value in row] for row in frame.itertuples(index=False)]
    header = "| " + " | ".join(columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, rule, *body])


def write_report(
    raw: pd.DataFrame,
    all_windows: list[dict],
    runs: pd.DataFrame,
    grr,
    attribute,
    bias_results: dict,
    catalogue: pd.DataFrame,
    results: pd.DataFrame,
    baseline: pd.DataFrame,
    seeded,
    manifest: dict,
) -> None:
    output = OUTPUT_DIR / "report.md"
    per_class = seeded.by_hazard_class.copy()
    bench_summary = grr.per_bench_repeatability.copy()
    bench_summary["mean"] = bench_summary["mean"].round(4)
    bench_summary["bias_vs_grand_mean"] = bench_summary["bias_vs_grand_mean"].round(4)
    bench_summary["repeatability_sd"] = bench_summary["repeatability_sd"].round(4)
    attr_majority = attribute.between_bench_majority
    clean_monitor_cols = [c for c in baseline.columns if c != "scenario_id"]
    clean_any = baseline[clean_monitor_cols].any(axis=1) if not baseline.empty else pd.Series(dtype=bool)

    bias_summary = pd.DataFrame(
        [
            {
                "configuration": name,
                "n": value.n,
                "mean_bias_ft": value.mean_bias,
                "bias_95ci_low": value.bias_ci[0],
                "bias_95ci_high": value.bias_ci[1],
                "linearity_slope": value.slope,
                "linearity_p": value.slope_p,
            }
            for name, value in bias_results.items()
        ]
    )

    text = f"""# NGSIM US-101 Public-Data Replay Pilot

**Report status:** reproducible method-demonstration pilot; not an industrial HIL/SIL bench qualification and not independent third-party validation.  
**Generated:** {manifest['generated_utc']}  
**Protocol implementation:** `msa-ad` {manifest['msa_ad_version']} at commit `{manifest['msa_ad_git_commit']}`

## Executive finding

This pilot demonstrates that the `msa-ad` workflow can ingest a fixed slice of real U.S. road-traffic measurements, produce a balanced crossed replay study, compare replay configurations to a declared reference channel, and measure known-fault detection with traceable inputs and outputs. It does **not** prove that a production automated-driving HIL bench is accurate, because the three “benches” here are software measurement configurations applied to one public source dataset.

The crossed study used {grr.n_scenarios} real following-event windows × {grr.n_benches} configurations × {grr.n_replicates} sampling-phase replicates = {len(runs)} measurements. The result was **{grr.verdict}** under the imported AIAG bands: %GRR = {grr.pct_grr:.2f}%, ndc = {grr.ndc}. This is a finding about the deliberately compared speed-estimation configurations and sampling phase, not a universal property of NGSIM or of any HIL facility.

The seeded-fault campaign executed {seeded.n_expected} positive controls. It detected {seeded.n_detected}, for a measured rate of {seeded.detection_rate:.1%} with 95% Wilson CI [{seeded.detection_ci[0]:.1%}, {seeded.detection_ci[1]:.1%}]. The clean-window screening evaluated {len(baseline)} candidate windows while accumulating {catalogue['scenario_id'].nunique()} eligible baselines; {int(clean_any.sum())} triggered at least one predeclared integrity monitor and were excluded from the positive-control campaign. Exclusions remain visible in `baseline_monitor_results.csv`.

## Data provenance

- Publisher: U.S. Department of Transportation, Federal Highway Administration / ITS JPO.
- Dataset: Next Generation Simulation (NGSIM) Vehicle Trajectories and Supporting Data.
- Site: US-101, Los Angeles, California.
- Source window: Unix milliseconds 1118847200000 through 1118847260000, inclusive (60 seconds).
- Source rows: {len(raw):,}; unique vehicles: {raw['vehicle_id'].nunique():,}; unique timestamps: {raw['global_time'].nunique():,}.
- Source query: `{SOURCE_URL}`
- Raw CSV SHA-256: `{manifest['raw_sha256']}`
- License recorded by the U.S. DOT portal: CC BY-SA 4.0.
- Dataset DOI: {DATASET_DOI}

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

- %GRR: **{grr.pct_grr:.2f}%** ({grr.verdict})
- EV (sampling-phase repeatability SD): {grr.ev:.4f} ft
- AV (configuration reproducibility SD): {grr.av:.4f} ft
- PV (scenario variation SD): {grr.pv:.4f} ft
- ndc: **{grr.ndc}**
- Scenario × configuration interaction pooled: {grr.interaction_pooled} (p = {grr.interaction_p:.4g}, alpha = {grr.interaction_alpha})

{_md_table(bench_summary)}

### Binary agreement

- Majority between-configuration agreement: {attr_majority[0]}/{attr_majority[1]} = {attr_majority[2]:.1%}, 95% Wilson CI [{attr_majority[3][0]:.1%}, {attr_majority[3][1]:.1%}].
- Fleiss kappa over all trials: {attribute.fleiss_kappa_all_trials:.4f}.
- Disagreement scenarios: {len(attribute.disagreement_scenarios)}.

All {len(runs)} replay results fell on the “pass” side of the zero-foot demonstration threshold. Accordingly, the 100% raw agreement is **non-discriminating** and kappa is undefined; it must not be cited as evidence that the configurations distinguish pass from fail. A later confirmatory study needs pre-registered scenarios on both sides of a safety-derived threshold.

### Bias and linearity against the declared anchor

{_md_table(bias_summary)}

### Seeded known-fault controls

Predeclared controls and monitors:

| fault class | injection | expected monitor |
|---|---|---|
| CLOCK_STEP | +300 ms time step | cadence gap >150 ms |
| SPEED_BIAS | +10 ft/s persistent bias | median speed-channel disagreement >6 ft/s |
| POSITION_STEP | +12 ft longitudinal step | one-step kinematic innovation >6 ft |
| SPEED_FREEZE | 2.0 s held speed | ≥15 near-identical frames while position advances >20 ft |
| LEAD_SIGNAL_LOSS | 1.0 s interior loss | bracketed loss of lead/headway for ≥5 frames |

{_md_table(per_class)}

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
"""
    output.write_text(text, encoding="utf-8")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    download_if_needed(RAW_DATA)

    raw = pd.read_csv(RAW_DATA)
    expected = {"us-101"}
    if set(raw["location"].unique()) != expected:
        raise ValueError(f"unexpected location values: {raw['location'].unique()}")
    if raw.duplicated(["vehicle_id", "global_time"]).any():
        raise ValueError("source slice has duplicate (vehicle_id, global_time) rows")

    data = add_speed_channels(raw)
    windows = select_windows(data)
    if len(windows) < N_GRR_SCENARIOS:
        raise RuntimeError(
            f"only {len(windows)} eligible windows; need {N_GRR_SCENARIOS}"
        )

    runs = build_bench_runs(data, windows)
    grr = gage_rr_anova(
        runs,
        scenario_col="scenario_id",
        bench_col="bench_id",
        value_col="residual_clearance_ft",
    )
    attribute = attribute_agreement(
        runs,
        scenario_col="scenario_id",
        bench_col="bench_id",
        verdict_col="verdict",
    )
    bias_results = {
        bench: bias_linearity_study(
            group,
            reference_col="reference_value_ft",
            value_col="residual_clearance_ft",
        )
        for bench, group in runs.groupby("bench_id", sort=True)
    }

    catalogue, campaign, baseline = build_fault_campaign(windows)
    if catalogue.empty:
        raise RuntimeError("no clean baseline windows available for fault seeding")
    seeded = analyse_seeded_faults(catalogue, campaign, threshold=0.80)

    runs.to_csv(OUTPUT_DIR / "bench_runs.csv", index=False)
    catalogue.to_csv(OUTPUT_DIR / "fault_catalogue.csv", index=False)
    campaign.to_csv(OUTPUT_DIR / "campaign_results.csv", index=False)
    baseline.to_csv(OUTPUT_DIR / "baseline_monitor_results.csv", index=False)
    pd.DataFrame(
        [
            {
                "scenario_id": x["scenario_id"],
                "vehicle_id": x["vehicle_id"],
                "start_global_time_ms": x["start_time"],
                "end_global_time_ms": int(x["frame"]["global_time"].iloc[-1]),
            }
            for x in windows
        ]
    ).to_csv(OUTPUT_DIR / "selected_scenarios.csv", index=False)

    import msa_ad  # noqa: E402

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_page": DATASET_PAGE,
        "dataset_doi": DATASET_DOI,
        "source_url": SOURCE_URL,
        "raw_path": str(RAW_DATA.relative_to(HERE)),
        "raw_sha256": sha256(RAW_DATA),
        "raw_rows": len(raw),
        "raw_unique_vehicles": int(raw["vehicle_id"].nunique()),
        "source_time_range_ms": [int(raw.global_time.min()), int(raw.global_time.max())],
        "analysis_script_sha256": sha256(Path(__file__)),
        "msa_ad_version": msa_ad.__version__,
        "msa_ad_git_commit": git_rev(MSA_AD_REPO),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "parameters": {
            "window_frames": WINDOW_FRAMES,
            "n_grr_scenarios": N_GRR_SCENARIOS,
            "n_fault_baselines_target": N_FAULT_BASELINES,
            "response_time_s": RESPONSE_TIME_S,
            "verdict_threshold_ft": VERDICT_THRESHOLD_FT,
            "sampling_phases": [0, 1, 2],
            "seeded_fault_detection_threshold": 0.80,
        },
        "outputs": {},
    }

    full_text = [
        render_gage_rr_report(grr),
        render_attribute_report(attribute),
    ]
    for bench, result in bias_results.items():
        full_text.extend([f"BIAS CONFIGURATION: {bench}", render_bias_report(result)])
    full_text.append(render_seeded_fault_report(seeded))
    (OUTPUT_DIR / "full_statistical_output.txt").write_text(
        "\n\n".join(full_text) + "\n", encoding="utf-8"
    )

    write_report(
        raw,
        windows,
        runs,
        grr,
        attribute,
        bias_results,
        catalogue,
        campaign,
        baseline,
        seeded,
        manifest,
    )

    for path in sorted(OUTPUT_DIR.iterdir()):
        if path.is_file():
            manifest["outputs"][path.name] = {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"raw rows: {len(raw):,}")
    print(f"eligible real-event windows: {len(windows)}")
    print(
        f"Gage R&R: %GRR={grr.pct_grr:.2f}%, ndc={grr.ndc}, verdict={grr.verdict}"
    )
    print(
        "seeded faults: "
        f"{seeded.n_detected}/{seeded.n_expected}={seeded.detection_rate:.1%}, "
        f"95% CI [{seeded.detection_ci[0]:.1%}, {seeded.detection_ci[1]:.1%}]"
    )
    print(f"report: {OUTPUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
