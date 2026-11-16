import json
from collections import Counter
from judgments_main import J,O
R=[json.loads(l) for l in open('results/ugen_results.jsonl',encoding='utf-8')]
def ans_verdict_for_gold(r):
    return J[r['id']][0] if r['choice_id']==r['principle'] else O[r['id']][0]
def ans_false(r):
    return J[r['id']][1] if r['choice_id']==r['principle'] else O[r['id']][1]
for st in ('failed','heldout'):
    S=[r for r in R if r['set']==st]
    gold=[r for r in S if r['coverage']!='none']
    emb=[r for r in gold if r['top5'][0]['id']==r['principle']]
    ev=Counter(ans_verdict_for_gold(r) for r in emb)
    print(st,'emb-top1 pipeline: emb correct',len(emb),'answers',dict(ev),'false',sum(ans_false(r) for r in emb))
    full=[r for r in emb if r['coverage']=='full']
    print('  of which gold full',len(full),dict(Counter(ans_verdict_for_gold(r) for r in full)))
    # oracle right
    orr=Counter(ans_verdict_for_gold(r) for r in gold); print(' oracle all gold',dict(orr))
    if st=='failed':
        ab=[r for r in gold if r['hub_verdict'] in('abstained','sensitive')]
        print(' oracle on abstained/sens',dict(Counter(ans_verdict_for_gold(r) for r in ab)),len(ab))
        ab2=[r for r in emb if r['hub_verdict'] in('abstained','sensitive')]
        print(' emb-top1 on abstained/sens',dict(Counter(ans_verdict_for_gold(r) for r in ab2)))
    # by lang oracle right
    for lang in('zh','en'):
        print(' ',lang,'oracle right',sum(ans_verdict_for_gold(r)=='right' for r in gold if r['lang']==lang),'emb-top1 right',sum(ans_verdict_for_gold(r)=='right' for r in emb if r['lang']==lang))
# oracle right in failed by gold coverage
