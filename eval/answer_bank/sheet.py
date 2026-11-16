import json,sys
sys.path.insert(0,'.')
qs=json.load(open('retrieval_top.json',encoding='utf-8'))
bank={d['id']:d for d in map(json.loads,open('bank_en.jsonl',encoding='utf-8'))}
pairs=[]
seen=set()
for q in qs:
    for n in ('1182','500','250'):
        iid,s=q['top'][n][0]
        if (q['id'],iid) in seen: continue
        seen.add((q['id'],iid)); pairs.append((q['id'],q['q'],iid,s))
print(len(pairs),file=sys.stderr)
for p in pairs:
    print(f"{p[0]}|{p[1]}|{p[2]} {bank[p[2]]['q']}|{p[3]:.2f}")
