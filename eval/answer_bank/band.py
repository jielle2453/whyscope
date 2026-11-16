import json, sys, collections
sys.path.insert(0, '.')
from judg import judge
qs = [q for q in json.load(open('retrieval_top.json', encoding='utf-8')) if q['set'] != 'user']
for lo, hi in ((0.6, 0.85), (0.6, 0.8)):
    c = collections.Counter(); c2 = collections.Counter()
    for q in qs:
        i, s = q['top']['1182'][0]
        if lo <= s < hi:
            c[judge(q['id'], i)] += 1; c2[q['set']] += 1
    print(lo, hi, dict(c), dict(c2))
print('below .6', sum(q['top']['1182'][0][1] < 0.6 for q in qs))
for q in qs:
    i, s = q['top']['1182'][0]
    if s >= 0.75 and judge(q['id'], i) == 'W':
        print(q['id'], q['q'], i, round(s, 2))
