# NetGuard Benchmark Suites

This directory contains benchmark data and evaluation scripts for NetGuard v2.0.

- `crv-bench`: cross-resource vulnerability scenarios.
- `br-bench`: blast-radius ground-truth annotations.
- `aiq-bench`: AI explanation quality data.
- `gd-bench`: graph diff correctness pairs.

Run metric scripts:

```bash
python benchmarks/scripts/evaluate_crv_br.py
python benchmarks/scripts/evaluate_aiq.py
python benchmarks/scripts/evaluate_gd.py
```
