"""Synthetic, privacy-free dataset for Molt's optional TabPFN advisory.
One row = summary statistics of one incoming CSV file. Label = 1 if that file later hit drift.
No names, emails, paths or cell values. Distributions overlap and 4% of labels are noisy, so the task is not trivial.
Usage: python make_tabpfn_dataset.py [rows] [seed]   ->  molt_drift_features.csv"""
import csv, random, sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
cols = ["row_count", "null_fraction", "unseen_category_fraction", "date_parse_fail_fraction",
        "decimal_parse_fail_fraction", "column_count_delta", "duplicate_fraction", "header_similarity", "is_drift"]
clip = lambda v: round(min(1.0, max(0.0, v)), 4)
rows = []
for _ in range(n):
    drift = rng.random() < 0.22
    kind = rng.choice(["rename", "category", "dates", "decimals", "columns"]) if drift else None
    rows.append([
        max(5, int(rng.gauss(400, 150))),
        clip(rng.gauss(0.03, 0.02) + (0.05 if kind == "columns" else 0)),
        clip(abs(rng.gauss(0.002, 0.004)) + (abs(rng.gauss(0.05, 0.04)) if kind == "category" else 0)),
        clip(abs(rng.gauss(0.002, 0.004)) + (abs(rng.gauss(0.08, 0.05)) if kind == "dates" else 0)),
        clip(abs(rng.gauss(0.002, 0.004)) + (abs(rng.gauss(0.06, 0.05)) if kind == "decimals" else 0)),
        rng.choice([0, 0, 0, 0, 1, -1]) if not drift else rng.choice([0, 0, 1, -1, -2, 2]),
        clip(rng.gauss(0.05, 0.03)),
        clip(rng.gauss(0.97, 0.03) - (rng.uniform(0.1, 0.5) if kind == "rename" else 0)),
        (1 - drift) if rng.random() < 0.04 else int(drift),  # label noise
    ])
with open("molt_drift_features.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols); w.writerows(rows)
pos = sum(r[-1] for r in rows)
print(f"wrote molt_drift_features.csv: {n} rows, {pos} drift ({pos / n:.0%})")