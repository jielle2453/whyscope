import json,sys
sys.path.insert(0,'.')
from judg import judge
qs=json.load(open('retrieval_top.json',encoding='utf-8'))
def stats(sel,size,T):
    ans=[(judge(q['id'],q['top'][size][0][0]),) for q in sel if q['top'][size][0][1]>=T]
    n=len(sel);a=len(ans);r=sum(x[0]=='R' for x in ans);p=sum(x[0]=='P' for x in ans);w=a-r-p
    return n,a,r,p,w
sets={'v3':[q for q in qs if q['set']=='v3'],'fresh':[q for q in qs if q['set']=='fresh']}
sets['all145']=sets['v3']+sets['fresh']
for size in ('1182','500','250'):
    print('SIZE',size)
    for T in (0.0,0.5,0.6,0.65,0.7,0.75,0.8,0.85,0.9):
        row=[]
        for k,sel in sets.items():
            n,a,r,p,w=stats(sel,size,T)
            row.append(f"{k}: ans {a}/{n} R{r} P{p} W{w} cov(R+P) {100*(r+p)/n:.0f}%")
        print(f"T={T}", " | ".join(row))
