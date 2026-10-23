# TabPFN proof note

TabPFN was used as a **local CPU inference package**, not through a hosted
TabPFN dashboard. The run therefore has no provider-usage dashboard receipt.
The reproducible proof is the code, package metadata, aggregate result file and
source-file fingerprints below.

## Recorded run

- Package: TabPFN **9.1.0**
- Model: default
- Device: CPU
- Dataset: 1,500-row synthetic, rule-generated labeled fixture
- Split: 1,200 training / 300 held out
- Target: `is_drift`; label `1`
- Rows scored: 300
- Rows flagged: 55
- True positives: 52
- False positives: 3
- True negatives: 225
- False negatives: 20
- Precision: 94.55%
- Recall: 72.22%
- Source rows changed: 0
- SHA-256 before and after: identical
- Elapsed time: 110.815 seconds

## Reproduction sources

- Result: `tabpfn-accuracy.json`
- Runner: `../tabpfn_accuracy.py`
- Integration: `../molt/anomaly.py`
- Tests: `../tests/test_anomaly.py`

The runner calls the TabPFN-backed `AnomalyAnalyzer` with TabPFN enabled and
exports only aggregate metrics. It suppresses diagnostic output and records no
row values, row numbers, per-row probabilities, credentials or exception text.

## Honest boundary

This is synthetic supervised holdout evaluation with rule-generated labels. It
is advisory only; it is not real-world validation, unlabeled anomaly detection,
or proof of usage in a hosted TabPFN dashboard.
