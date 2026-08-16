# NGSIM public-road-data replay pilot

This directory contains a reproducible method-demonstration pilot for
`msa-ad`. It uses a fixed 60-second slice of the U.S. DOT/FHWA NGSIM US-101
trajectory dataset.

Run, from a checkout of this repository with `numpy`, `scipy` and `pandas`
installed:

```bash
cd example/ngsim_pilot
python run_pilot.py
```

The script uses the committed public-data slice at `data/ngsim_us101_60s.csv`
(and re-downloads the exact slice from the source API if that file is absent),
then writes the audit package under `outputs/`. Before treating a fresh
download as identical to the committed slice, compare its SHA-256 against
`outputs/manifest.json`.

This is deliberately described as a **public real-data replay pilot**, not as
an industrial HIL/SIL validation. See `outputs/report.md` for claim boundaries.

Data source: U.S. DOT/FHWA, *Next Generation Simulation (NGSIM) Vehicle
Trajectories and Supporting Data*, DOI
[10.21949/1504477](https://doi.org/10.21949/1504477). The source portal records
the dataset license as CC BY-SA 4.0, which applies to the data slice in
`data/` and not to the `msa-ad` software; see `DATA_LICENSE.md`.
