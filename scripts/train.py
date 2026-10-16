"""Official Texas Lottery data -> leak-free chronological evaluation -> predictions JSON."""
import csv, io, json, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import log_loss

BASE='https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/Winning_Numbers/'
GAMES=['morning','day','evening','night']
ROOT=Path(__file__).resolve().parents[1]
WINDOW=40

def parse(data, game):
    records=[]
    for row in csv.reader(io.StringIO(data)):
        if len(row)<7: continue
        try:
            month,day,year=map(int,row[1:4]); digits=tuple(int(x) for x in row[4:7])
            if any(x not in range(10) for x in digits): continue
            dt=datetime(year,month,day)
            records.append((dt,digits))
        except (ValueError,TypeError): continue
    return sorted(dict(records).items())

def features(history):
    """Only prior draws, never the draw being predicted."""
    prior=np.array(history[-WINDOW:],dtype=float)
    vals=[]
    for pos in range(3):
        seq=prior[:,pos].astype(int)
        for length in (10,20,40):
            counts=np.bincount(seq[-length:],minlength=10)/length
            vals.extend(counts.tolist())
        vals.extend((seq[-5:]/9).tolist())
    sums=prior.sum(axis=1)
    vals += [float(np.mean(sums))/27,float(np.std(sums))/14]
    return vals

def build(rows):
    nums=[r[1] for r in rows]
    X=np.asarray([features(nums[:i]) for i in range(WINDOW,len(nums))])
    y=np.asarray(nums[WINDOW:])
    return X,y

def predict_one(rows):
    if len(rows)<WINDOW+120: raise ValueError('Insufficient history for ML training')
    X,y=build(rows)
    split=int(len(X)*0.8)
    if split<100 or len(X)-split<20:raise ValueError('Insufficient chronological test data')
    out=[]; metrics=[]
    for p in range(3):
        model=RandomForestClassifier(n_estimators=120,max_depth=6,min_samples_leaf=15,
                                     random_state=240+p,n_jobs=-1)
        model.fit(X[:split],y[:split,p]); prob=model.predict_proba(X[split:])
        full=np.zeros((len(prob),10))
        for j,digit in enumerate(model.classes_):full[:,int(digit)]=prob[:,j]
        full=np.maximum(full,1e-6);full/=full.sum(axis=1,keepdims=True)
        model_loss=float(log_loss(y[split:,p],full,labels=list(range(10))))
        baseline=np.bincount(y[:split,p],minlength=10)+1
        baseline=baseline/baseline.sum()
        base_loss=float(log_loss(y[split:,p],np.tile(baseline,(len(prob),1)),labels=list(range(10))))
        # Deploy only if retrospective holdout improves on baseline, else baseline.
        if model_loss<base_loss:
            model.fit(X,y[:,p]); current=np.zeros(10)
            for digit,v in zip(model.classes_,model.predict_proba([features([r[1] for r in rows])])[0]):
                current[int(digit)]=v
            chosen='random_forest'
        else:
            current=(np.bincount(y[:,p],minlength=10)+1).astype(float)
            chosen='smoothed_frequency'
        current=np.maximum(current,1e-6);current/=current.sum()
        out.append([round(float(x),9) for x in current]);
        metrics.append({'position':p+1,'model_log_loss':round(model_loss,4),'baseline_log_loss':round(base_loss,4),'selected':chosen})
    return {'draws':len(rows),'last_draw':rows[-1][0].date().isoformat(),
            'recent':[''.join(map(str,ds)) for _,ds in rows[-40:][::-1]],
            'probabilities':out,'validation':metrics,'holdout_draws':len(X)-split}

def main():
    payload={'generated_at':datetime.now(timezone.utc).isoformat(), 'source':BASE,'games':{}}
    for game in GAMES:
        url=BASE+f'pick3{game}.csv'
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PICK3-AI/1.0'}),timeout=35) as resp:
            text=resp.read().decode('utf-8-sig')
        rows=parse(text,game)
        obj=predict_one(rows)
        obj['source_url']=url
        payload['games'][game]=obj
        print(game,obj['draws'],obj['last_draw'],[m['selected'] for m in obj['validation']])
    target=ROOT/'web'/'data'/'predictions.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            previous=json.loads(target.read_text(encoding='utf-8'))
            if all(previous['games'][game]['last_draw']==payload['games'][game]['last_draw'] and
                   previous['games'][game]['recent']==payload['games'][game]['recent'] for game in GAMES):
                print('No new official draws; preserving previous model output')
                return
        except (ValueError, KeyError, TypeError):
            pass
    target.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print('wrote',target)
if __name__=='__main__':main()
