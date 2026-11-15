
import json,collections,re,sys
import numpy as np
from rank_bm25 import BM25Okapi
D=sys.argv[1]
def rd(f):
    d=collections.defaultdict(set)
    for l in open(f):
        a,b=l.split(); d[a].add(b)
    return d
tok=lambda s:[w for w in re.findall(r"[a-z0-9]+",s.lower()) if len(w)>1]
corpus={json.loads(l)['_id']:json.loads(l)['text'] for l in open(D+'/corpus.jsonl')}
queries={json.loads(l)['_id']:json.loads(l)['text'] for l in open(D+'/queries.jsonl')}
tr=rd(D+'/query_tool_train.txt'); te=rd(D+'/query_tool_test.txt')
ids=list(corpus); bm=BM25Okapi([tok(corpus[i]) for i in ids])
te_ids=list(te)[:600]
cache={q:bm.get_scores(tok(queries[q])) for q in te_ids}
trq=list(tr)
def evalk(fn,k):
    rec=comp=0
    for q in te_ids:
        top=fn(q)[:k]; g=te[q]; h=len(g&set(top)); rec+=h/len(g); comp+=h==len(g)
    return round(rec/len(te_ids),3), round(comp/len(te_ids),3)
for n in [0,2000,5000,10000,len(trq)]:
    past=trq[:n]
    qbm=BM25Okapi([tok(queries[q]) for q in past]) if n else None
    def fn(q):
        s=cache[q]; o=np.argsort(-s)[:20]; mx=s[o[0]] or 1
        sc=collections.Counter()
        for i in o: sc[ids[i]]+=s[i]/mx
        if qbm:
            ps=qbm.get_scores(tok(queries[q])); po=np.argsort(-ps)[:5]; pm=ps[po[0]] or 1
            for j in po:
                for t in tr[past[j]]: sc[t]+=1.5*ps[j]/pm
        return [t for t,_ in sc.most_common(50)]
    print('n=',n, 'R@5,C@5',evalk(fn,5),'R@10,C@10',evalk(fn,10), flush=True)
