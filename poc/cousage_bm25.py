
import json,collections,re,math,sys
from rank_bm25 import BM25Okapi
D=sys.argv[1]
def rd(f):
    d=collections.defaultdict(set)
    for l in open(f):
        a,b=l.split(); d[a].add(b)
    return d
tok=lambda s:[w for w in re.findall(r"[a-z0-9]+",s.lower()) if len(w)>1]
corpus={}
for l in open(D+'/corpus.jsonl'):
    j=json.loads(l); corpus[j['_id']]=j['text']
queries={}
for l in open(D+'/queries.jsonl'):
    j=json.loads(l); queries[j['_id']]=j['text']
tr=rd(D+'/query_tool_train.txt'); te=rd(D+'/query_tool_test.txt')
ids=list(corpus); bm=BM25Okapi([tok(corpus[i]) for i in ids])
import numpy as np
te_ids=list(te)[:800]
def bmscores(q): return bm.get_scores(tok(queries[q]))
cache={q:bmscores(q) for q in te_ids}
def evalk(rank_fn,k=5):
    rec=comp=0
    for q in te_ids:
        top=rank_fn(q)[:k]; g=te[q]; h=len(g&set(top)); rec+=h/len(g); comp+= h==len(g)
    return round(rec/len(te_ids),3), round(comp/len(te_ids),3)
def base(q):
    s=cache[q]; o=np.argsort(-s); return [ids[i] for i in o[:50]]
print('bm25', evalk(base,5), evalk(base,10))
trq=list(tr)
for n in [0,1000,3000,10000,len(trq)]:
    co=collections.defaultdict(lambda: collections.Counter())
    for q in trq[:n]:
        g=list(tr[q])
        for a in g:
            for b in g:
                if a!=b: co[a][b]+=1
    def exp(q):
        s=cache[q]; o=np.argsort(-s)[:10]; seeds=[ids[i] for i in o]
        mx=s[o[0]] or 1
        sc=collections.Counter()
        for r,i in enumerate(o):
            sc[ids[i]]+=s[i]/mx
            tot=sum(co[ids[i]].values()) or 1
            for b,c in co[ids[i]].most_common(10): sc[b]+= (s[i]/mx)*c/tot
        return [t for t,_ in sc.most_common(50)]
    print('cousage n=',n, evalk(exp,5), evalk(exp,10))
