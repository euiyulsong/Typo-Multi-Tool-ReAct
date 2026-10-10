"""Offline control-flow and evaluator regression tests; no model/API evaluation."""
import argparse, json
import benchmark as b

class FakeAPI:
    def __init__(self,a): self.a=a; self.calls=0; self.tokens=0; self.seconds=0
    def call(self,messages,tools=None):
        self.calls+=1
        if tools is None: return {'role':'assistant','content':json.dumps({'text':self.a.row['clean']})}
        row=self.a.row; gold=b.gold_calls(row)
        groups=[gold] if row['suite']=='parallel' else [gold[:2],gold[2:5],gold[5:]]
        index=sum(m['role']=='assistant' for m in messages)
        assert index<len(groups)
        if index>0: assert any(m['role']=='tool' for m in messages)
        return {'role':'assistant','content':None,'tool_calls':[{'id':str(index)+'_'+str(i),'type':'function','function':{'name':c['name'],'arguments':json.dumps(c['arguments'])}} for i,c in enumerate(groups[index])]}

b.API=FakeAPI
records=[]
for row in b.dataset(100,42):
    a=argparse.Namespace(max_steps=8,row=row)
    for mode in ['one_shot','react']:
        for variant in ['clean','raw','llm','term']:
            r=b.run_one(row,variant,a,mode)
            expected=int(mode=='react' or row['suite']=='parallel')
            assert r['task_success']==expected and r['error'] is None,r
            assert r['first_step_call_exact']==1
            assert r['call_multiset_exact']==expected
            expected_agent_calls=1 if mode=='one_shot' or row['suite']=='parallel' else 3
            assert r['llm_calls']==expected_agent_calls+(variant=='llm')
            assert len(r['executed'])==(3 if row['suite']=='parallel' else 6 if mode=='react' else 2)
            if not expected: assert r['failure_reason']=='missing_or_incorrect_required_calls'
            records.append(r)
    if row['suite']=='parallel':
        gold=b.gold_calls(row)
        for missing in range(3):
            bad=b.Sandbox(row)
            for i,c in enumerate(gold):
                if i!=missing: bad.execute(c['name'],c['arguments'])
            assert not bad.success
        for incorrect in range(3):
            bad=b.Sandbox(row)
            for i,c in enumerate(gold):
                args=dict(c['arguments'])
                if i==incorrect:
                    key='destination' if i==0 else 'city'; args[key]=row['origin']
                bad.execute(c['name'],args)
            assert not bad.success
        bad=b.Sandbox(row)
        assert 'error' in bad.execute('hotel_lookup',{'city':row['destination'],'nights':True})
summary=b.summarize(records)
assert len(summary)==72
for r in summary:
    if r['suite']=='parallel': assert r['task_success']==1
    if r['suite']=='dependent' and r['mode']=='one_shot': assert r['task_success']==0
    if r['mode']=='react': assert r['task_success']==1
class BrokenAPI(FakeAPI):
    def call(self,messages,tools=None): return {'role':'assistant','content':'not json'}
b.API=BrokenAPI
assert b.run_one(row,'llm',a)['error'] is not None
print('PASS: 800 mocked episodes, parallel one-shot successes, dependent incomplete failures, missing/wrong arguments, correction overhead, 72 summary groups.')
