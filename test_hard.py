"""Executable oracle and mocked loop controls, no model quality claims."""
import argparse, copy, json
import hard
b=hard.b

def check():
 rows=hard.dataset(100,42)
 assert rows==hard.dataset(100,42)
 assert len({r['clean'] for r in rows})==100
 assert all(r['clean']!=r['noisy'] for r in rows)
 assert all(len(r['gold_calls'])==8 and len(r['menu'])==15 for r in rows)
 assert len({g['name'] for r in rows for g in r['gold_calls']})==10
 records=[]
 class Fake:
  def __init__(self,a):self.a=a;self.calls=0;self.tokens=0;self.seconds=0
  def call(self,messages,tools=None):
   self.calls+=1
   if tools is None:return {'role':'assistant','content':json.dumps({'text':self.a.row['clean']})}
   gold=self.a.row['gold_calls']
   return {'role':'assistant','content':None,'tool_calls':[{'id':str(i),'type':'function','function':{'name':g['name'],'arguments':json.dumps(g['arguments'])}} for i,g in enumerate(gold)]}
 b.API=Fake
 for row in rows:
  gold=row['gold_calls'];s=hard.Sandbox(row)
  for g in gold:assert 'error' not in s.execute(g['name'],g['arguments'])
  assert s.success
  for omit in range(8):
   s=hard.Sandbox(row)
   for i,g in enumerate(gold):
    if i!=omit:s.execute(g['name'],g['arguments'])
   assert not s.success
  bad=copy.deepcopy(gold);bad[0]['arguments']['passengers']+=1;s=hard.Sandbox(row)
  for g in bad:s.execute(g['name'],g['arguments'])
  assert not s.success
  s=hard.Sandbox(row)
  s.execute('flight_reserve',gold[0]['arguments'])
  for g in gold:s.execute(g['name'],g['arguments'])
  assert not s.success
  for mode in ['one_shot','react']:
   for variant in ['clean','raw','llm','term']:
    result=b.run_one(row,variant,argparse.Namespace(max_steps=8,row=row),mode)
    assert result['task_success']==1 and result['first_step_call_f1']==1
    assert result['call_multiset_exact']==1 and result['llm_calls']==1+(variant=='llm')
    records.append(result)
 assert len(b.summarize(records))==48
 print('PASS: 100 diverse hard cases, 800 mock episodes, all eight required calls, missing/wrong arguments and excluded reservation rejection.')
if __name__=='__main__':check()
