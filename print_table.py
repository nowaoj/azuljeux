import csv
with open('raw_greedy_vs_planned.csv', newline='') as f:
    data = list(csv.DictReader(f))
print("| Seed | ScoreA | ScoreB | PenA  | PenB  | RowA  | RowB  | ColA  | ColB  | SetA  | SetB  | Win |")
print("|------|--------|--------|-------|-------|-------|-------|-------|-------|-------|-------|-----|")
for r in data:
    w = 'A' if r['winner']=='0' else ('B' if r['winner']=='1' else 'T')
    print(f"| {r['seed']:>4} | {r['score_a']:>6} | {r['score_b']:>6} | {r['penalty_a']:>5} | {r['penalty_b']:>5} | {r['rows_a']:>5} | {r['rows_b']:>5} | {r['cols_a']:>5} | {r['cols_b']:>5} | {r['colours_a']:>5} | {r['colours_b']:>5} | {w:>3} |")
