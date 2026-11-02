# Benchmark environment

Written by `tests/benchmarks/test_merge_performance.py` (requirement 32.11).
Recorded at 2026-11-01T21:28:47+00:00.

| Field | Value |
|-------|-------|
| CPU | AMD Ryzen 7 5825U with Radeon Graphics (8 cores, 16 threads) |
| RAM | 15.4 GB |
| Operating system | Windows-10-10.0.26200-SP0 |
| Python | 3.11.3 (tags/v3.11.3:f3909b8, Apr  4 2023, 23:49:59) [MSC v.1934 64 bit (AMD64)] |
| PySide6 / Qt | 6.11.1 / 6.11.1 |
| Qt platform | offscreen |
| Power plan | Power Scheme GUID: 81e4b121-a3e5-4e67-8579-9399bcc457a7  (Acer) |
| Seed and sizes | 20240607; 20,000 persons; 2,000 candidates |
| Runs | warm-up 3 (discarded); measured 30 / 10 / 5 |
| Figures reported | median, p95 (nearest rank), maximum; gate on the maximum |

## Results

| Metric | Median | p95 | Max | Limit or target | Kind |
|--------|--------|-----|-----|-----------------|------|
| Candidate index build | 6.7 ms | 13.0 ms | 16.0 ms | < 50 ms | target, not gated |
| Candidate index build + colour of all involved persons | 49.0 ms | 104.4 ms | 106.1 ms | < 1000 ms (on max) | gated |
| Person list indicators (index + colour of all 20,000 persons; upper bound of the extra cost) | 83.1 ms | 177.2 ms | 198.0 ms | < 20 ms | target, not gated |
| Comparison views (set_slot, refresh of both views and table, grab) | 1564.6 ms | 1973.4 ms | 1973.4 ms | < 2000 ms (on max) | gated |
| Merge_Plan build (regression guard on median) | 11789.4 ms | 17412.0 ms | 17412.0 ms | - | recorded |
