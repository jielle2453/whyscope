import json,urllib.request,time,sys
sys.path.insert(0,'.')
LO,HI=0.60,0.85
qs=json.load(open('retrieval_top.json',encoding='utf-8'))
bank={d['id']:d for d in map(json.loads,open('bank_en.jsonl',encoding='utf-8'))}
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SYS=("You talk to a child aged 5 to 8. Answer the child's question in one or two short, simple, kind sentences, "
     "using ONLY the facts in the Reference. Do not add any other facts. If the Reference does not answer the child's exact question, "
     "reply exactly: I don't know that one yet.")
def cm(r,c): return f"<|im_start|>{r}\n{c}<|im_end|>\n"
out=[]
for q in qs:
    if q['set']=='user': continue
    iid,s=q['top']['1182'][0]
    if not (LO<=s<HI): continue
    d=bank[iid]
    turn=cm('user',f"Reference: {d['q']} {d['a1']} {d['a2']}\n\nChild's question: {q['q']}")+"<|im_start|>assistant\n"
    body=json.dumps({"prefix":cm('system',SYS),"turn":turn,"max_new":70,"stop":{"ends":".!?","n":2},"priority":"high"}).encode()
    t=time.perf_counter()
    req=urllib.request.Request("http://127.0.0.1:8711/complete",body,{"Content-Type":"application/json"})
    r=json.loads(op.open(req,timeout=120).read())
    out.append({"id":q['id'],"q":q['q'],"item":iid,"score":s,"ref":d['a1']+" "+d['a2'],"ans":r['text'].strip(),"ms":(time.perf_counter()-t)*1000,"worker_ms":r.get('ms')})
    print(out[-1]['id'],round(out[-1]['ms']),flush=True)
    time.sleep(0.5)
json.dump(out,open('armc_results.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
