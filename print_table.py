import csv
with open('raw_planned_vs_random.csv', newline='') as f:
    data = list(csv.DictReader(f))
h = list(data[0].keys())
header = " | ".join(f"{c:<10}" for c in h)
print("| " + header + " |")
print("|" + "|".join("-" * 12 for _ in h) + "|")
for r in data:
    vals = [str(r[c]) for c in h]
    print("| " + " | ".join(f"{v:>10}" for v in vals) + " |")

