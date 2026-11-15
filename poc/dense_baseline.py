
import json,collections,sys,numpy as np
from fastembed import TextEmbedding
D=sys.argv[1]
def rd(f):
    d=collections.defaultdict(set)
    for l in open(f):
        a,b=l.split(); d[a].add(b)
    return d
corpus={json.loads(l)['_id']:json.loads(l)['text'] for l in open(D+'/corpus.jsonl')}
queries={json.loads(l)['_id']:json.loads(l)['text'] for l in open(D+'/queries.jsonl')}
te=rd(D+'/query_tool_test.txt'); tr=rd(D+'/query_tool_train.txt')
m=TextEmbedding('BAAI/bge-small-en-v1.5')
ids=list(corpus); E=np.array(list(m.embed([corpus[i][:1000] for i in ids])))
te_ids=list(te)[:600]
Q=np.array(list(m.embed(['Represent this sentence for searching relevant passages: '+queries[q] for q in te_ids])))
S=Q@E.T
for k in (5,10):
    rec=comp=0
    for qi,q in enumerate(te_ids):
        top=set(ids[i] for i in np.argsort(-S[qi])[:k]); g=te[q]; h=len(g&top); rec+=h/len(g); comp+=h==len(g)
    print('dense k',k, round(rec/600,3), round(comp/600,3), flush=True)
trq=list(tr)[:10000]
T=np.array(list(m.embed([queries[q] for q in trq])))
Q2=np.array(list(m.embed([queries[q] for q in te_ids])))
P=Q2@T.T
for k in (5,10):
    rec=comp=0
    for qi,q in enumerate(te_ids):
        sc=collections.Counter()
        for i in np.argsort(-S[qi])[:20]: sc[ids[i]]+=S[qi,i]
        for j in np.argsort(-P[qi])[:5]:
            for t in tr[trq[j]]: sc[t]+=1.5*P[qi,j]
        top=set(t for t,_ in sc.most_common(k)); g=te[q]; h=len(g&top); rec+=h/len(g); comp+=h==len(g)
    print('dense+flat-memory(10k) k',k, round(rec/600,3), round(comp/600,3), flush=True)
