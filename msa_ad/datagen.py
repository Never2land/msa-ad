"""Synthetic example-data generator.

Everything produced here is **synthetic**. It is not measured data from any
bench, programme or vehicle, and no part of it should be read as an
observation about any real system. It exists so that the example runs
reproducibly and so that the tooling can be seen finding something.

The data is deliberately constructed to contain findings:

* bench ``HIL-C`` has roughly 4x the within-scenario repeatability standard
  deviation of the other two benches, and a small positive bias;
* several scenarios sit close to the pass/fail threshold, so the binary
  verdicts disagree between benches on exactly those scenarios;
* the ``perception_false_negative`` hazard class has a poor seeded-fault
  detection rate, while other classes are good but seeded too sparsely to
  defend a 0.80 lower bound.

A demonstration in which everything passes demonstrates nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_SEED",
    "TTC_PASS_THRESHOLD_S",
    "generate_bench_runs",
    "generate_fault_catalogue",
    "generate_campaign_results",
    "generate_all",
]

DEFAULT_SEED = 20240517

#: Scenario passes when the observed minimum time-to-collision is at or above
#: this value, in seconds. Arbitrary, chosen for the example only.
TTC_PASS_THRESHOLD_S = 1.50

BENCHES = ["HIL-A", "HIL-B", "HIL-C"]

#: Per-bench systematic offset on minimum TTC, in seconds.
BENCH_BIAS_S = {"HIL-A": 0.00, "HIL-B": -0.06, "HIL-C": 0.15}

#: Per-bench within-scenario repeatability standard deviation, in seconds.
#: HIL-C is the deliberately degraded bench.
BENCH_REPEAT_SD_S = {"HIL-A": 0.08, "HIL-B": 0.10, "HIL-C": 0.35}

#: True (population) minimum-TTC level of each scenario, in seconds. Several
#: are placed near TTC_PASS_THRESHOLD_S so that verdicts can disagree.
SCENARIO_TRUE_TTC_S = {
    "CUT_IN_60KPH": 1.42,
    "CUT_IN_100KPH": 1.05,
    "LEAD_BRAKE_HARD": 1.18,
    "LEAD_BRAKE_MODERATE": 2.35,
    "PED_CROSS_OCCLUDED": 1.55,
    "PED_CROSS_OPEN": 2.80,
    "CYCLIST_OVERTAKE": 1.62,
    "MERGE_DENSE": 1.48,
    "MERGE_SPARSE": 3.05,
    "STATIONARY_OBSTACLE": 1.95,
    "ONCOMING_INTRUSION": 1.28,
    "ROUNDABOUT_YIELD": 2.60,
    "LANE_DROP": 2.15,
    "TRAFFIC_LIGHT_DILEMMA": 1.72,
    "DEBRIS_AVOIDANCE": 3.20,
}

#: Hazard classes, number of faults seeded, and the number the campaign
#: detects. Counts are fixed rather than sampled so the example is exactly
#: reproducible.
HAZARD_CLASSES = {
    "perception_false_negative": {"seeded": 40, "detected": 22},
    "planning_timing": {"seeded": 30, "detected": 28},
    "actuation_fault": {"seeded": 25, "detected": 24},
    "sensor_dropout": {"seeded": 25, "detected": 25},
}

INJECTION_POINTS = {
    "perception_false_negative": [
        "camera_object_list",
        "radar_track_list",
        "fusion_output",
    ],
    "planning_timing": ["planner_cycle_budget", "trajectory_publish_delay"],
    "actuation_fault": ["brake_torque_command", "steering_angle_command"],
    "sensor_dropout": ["lidar_frame_stream", "radar_frame_stream", "can_bus"],
}

#: Faults injected outside the declared ODD; detection is not claimed for them.
UNCLAIMED_FAULTS = [
    ("F-OOD-001", "HZ-OOD-01", "sensor_dropout", "lidar_frame_stream", True),
    ("F-OOD-002", "HZ-OOD-02", "perception_false_negative", "fusion_output", False),
    ("F-OOD-003", "HZ-OOD-03", "actuation_fault", "brake_torque_command", False),
    ("F-OOD-004", "HZ-OOD-04", "planning_timing", "planner_cycle_budget", True),
]

#: Faults catalogued but never run in the campaign.
N_NOT_EXECUTED = 5


def generate_bench_runs(
    seed: int = DEFAULT_SEED, n_replicates: int = 3
) -> pd.DataFrame:
    """Generate synthetic bench-run data.

    Returns one row per execution with a continuous metric
    (``min_ttc_s``) and the binary verdict derived from it by threshold.
    Deriving the verdict from the metric is deliberate: it is how a real
    campaign works, and it means the same file exercises both the continuous
    and the attribute analysis path.
    """
    rng = np.random.default_rng(seed)
    rows = []
    scenarios = list(SCENARIO_TRUE_TTC_S)

    # Scenario-by-bench interaction: a small effect fixed per cell.
    interaction = {
        (s, b): float(rng.normal(0.0, 0.06))
        for s in scenarios
        for b in BENCHES
    }

    for scenario in scenarios:
        true_ttc = SCENARIO_TRUE_TTC_S[scenario]
        for bench in BENCHES:
            cell_mean = true_ttc + BENCH_BIAS_S[bench] + interaction[(scenario, bench)]
            for rep in range(1, n_replicates + 1):
                value = float(
                    rng.normal(cell_mean, BENCH_REPEAT_SD_S[bench])
                )
                rows.append(
                    {
                        "scenario_id": scenario,
                        "bench_id": bench,
                        "replicate": rep,
                        "random_seed": int(rng.integers(1, 10**6)),
                        "min_ttc_s": round(value, 4),
                        "verdict": "pass" if value >= TTC_PASS_THRESHOLD_S else "fail",
                    }
                )
    return pd.DataFrame(rows)


def generate_fault_catalogue(seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Generate a synthetic seeded-fault catalogue."""
    rng = np.random.default_rng(seed + 1)
    rows = []
    for hazard_class, spec in HAZARD_CLASSES.items():
        points = INJECTION_POINTS[hazard_class]
        prefix = "".join(w[0] for w in hazard_class.split("_")).upper()
        for i in range(1, spec["seeded"] + 1):
            rows.append(
                {
                    "fault_id": f"F-{prefix}-{i:03d}",
                    "hazard_id": f"HZ-{prefix}-{((i - 1) % 6) + 1:02d}",
                    "hazard_class": hazard_class,
                    "injection_point": points[(i - 1) % len(points)],
                    "expected_detection": True,
                }
            )
    for fid, hid, hclass, point, _ in UNCLAIMED_FAULTS:
        rows.append(
            {
                "fault_id": fid,
                "hazard_id": hid,
                "hazard_class": hclass,
                "injection_point": point,
                "expected_detection": False,
            }
        )
    for i in range(1, N_NOT_EXECUTED + 1):
        hazard_class = list(HAZARD_CLASSES)[i % len(HAZARD_CLASSES)]
        rows.append(
            {
                "fault_id": f"F-PEND-{i:03d}",
                "hazard_id": f"HZ-PEND-{i:02d}",
                "hazard_class": hazard_class,
                "injection_point": INJECTION_POINTS[hazard_class][0],
                "expected_detection": True,
            }
        )
    df = pd.DataFrame(rows)
    # Shuffle so the file does not look sorted by outcome.
    return df.sample(frac=1.0, random_state=int(rng.integers(0, 10**6))).reset_index(
        drop=True
    )


def generate_campaign_results(
    catalogue: pd.DataFrame, seed: int = DEFAULT_SEED
) -> pd.DataFrame:
    """Generate synthetic campaign outcomes for a fault catalogue.

    Detection counts per hazard class are fixed (see :data:`HAZARD_CLASSES`);
    only *which* faults escape is chosen at random from the fixed seed.
    """
    rng = np.random.default_rng(seed + 2)
    detected_map: dict[str, bool] = {}

    claimed = catalogue.loc[
        catalogue["expected_detection"] & ~catalogue["fault_id"].str.startswith("F-PEND")
    ]
    for hazard_class, spec in HAZARD_CLASSES.items():
        ids = sorted(
            claimed.loc[claimed["hazard_class"] == hazard_class, "fault_id"]
        )
        n_detected = spec["detected"]
        chosen = set(
            rng.choice(np.array(ids), size=n_detected, replace=False).tolist()
        )
        for fid in ids:
            detected_map[fid] = fid in chosen

    for fid, _, _, _, detected in UNCLAIMED_FAULTS:
        detected_map[fid] = detected

    rows = [
        {
            "fault_id": fid,
            "campaign_id": "CAMP-2024-Q2",
            "detected": detected_map[fid],
        }
        for fid in catalogue["fault_id"]
        if fid in detected_map
    ]
    return pd.DataFrame(rows)


def generate_all(seed: int = DEFAULT_SEED) -> dict[str, pd.DataFrame]:
    """Generate every example table in one call."""
    runs = generate_bench_runs(seed)
    catalogue = generate_fault_catalogue(seed)
    results = generate_campaign_results(catalogue, seed)
    return {
        "bench_runs": runs,
        "fault_catalogue": catalogue,
        "campaign_results": results,
    }
