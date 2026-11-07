"""
Divide los 100 leads en dev (30) y test (70) de forma estratificada
por case_type con semilla fija. Guarda eval/split.json.
"""

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

SEED       = 42
DEV_TARGET = 30
GT_PATH    = Path(__file__).resolve().parent / "ground_truth.csv"
OUT_PATH   = Path(__file__).resolve().parent / "split.json"

# ── Cargar y agrupar por case_type ────────────────────────────────────────────
by_case: dict[str, list[int]] = defaultdict(list)
with open(GT_PATH, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        by_case[row["case_type"]].append(int(row["lead_id"]))

total = sum(len(v) for v in by_case.values())
assert total == 100, f"Se esperaban 100 leads, hay {total}"

# ── Split estratificado — método del mayor residuo ────────────────────────────
# Garantiza exactamente DEV_TARGET leads respetando las proporciones por clase.
rng = random.Random(SEED)

for ids in by_case.values():
    ids.sort()          # orden determinista previo a la mezcla
    rng.shuffle(ids)

fraction = DEV_TARGET / total   # 0.30

floors = {ct: int(len(ids) * fraction) for ct, ids in by_case.items()}
remaining = DEV_TARGET - sum(floors.values())

# Ordenar por residuo descendente; en empates, orden alfabético (determinismo)
residuals = {ct: len(ids) * fraction - floors[ct] for ct, ids in by_case.items()}
for ct in sorted(residuals, key=lambda k: (-residuals[k], k)):
    if remaining == 0:
        break
    floors[ct] += 1
    remaining -= 1

assert sum(floors.values()) == DEV_TARGET

# ── Construir listas ──────────────────────────────────────────────────────────
dev_ids, test_ids = [], []
for ct in sorted(by_case):
    ids   = by_case[ct]
    n_dev = floors[ct]
    dev_ids.extend(ids[:n_dev])
    test_ids.extend(ids[n_dev:])

dev_ids.sort()
test_ids.sort()

assert len(dev_ids)  == DEV_TARGET
assert len(test_ids) == total - DEV_TARGET
assert set(dev_ids) | set(test_ids) == set(range(1, total + 1))

# ── Guardar ───────────────────────────────────────────────────────────────────
OUT_PATH.write_text(json.dumps({"dev": dev_ids, "test": test_ids}, indent=2), encoding="utf-8")

print(f"Split guardado en {OUT_PATH}")
print(f"  dev : {len(dev_ids)} leads")
print(f"  test: {len(test_ids)} leads\n")

print(f"{'case_type':<25} {'total':>5} {'dev':>5} {'test':>5}  frac")
for ct in sorted(by_case):
    nd  = floors[ct]
    n   = len(by_case[ct])
    nt  = n - nd
    print(f"{ct:<25} {n:>5} {nd:>5} {nt:>5}  {nd/n:.0%}")
