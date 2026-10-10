#!/usr/bin/env python3
"""Paired typo ablation with real deterministic sandbox tool execution."""
import argparse, collections, concurrent.futures, hashlib, json, os, random, re, statistics, time, urllib.request
from pathlib import Path

CITIES = ['Seoul','Tokyo','Osaka','Busan','Paris','London','Berlin','Madrid','Rome','Sydney']
BENCHMARK_VERSION = 3
DESCRIPTIONS = {
 'flight_lookup': ('Get flight price in USD using origin and destination city names.', {'origin':'string','destination':'string'}),
 'hotel_lookup': ('Get hotel price in USD using city name and nights.', {'city':'string','nights':'integer'}),
 'weather_lookup': ('Get weather forecast using city name.', {'city':'string'}),
 'resolve_city': ('Resolve a city name into its city_id.', {'name':'string'}),
 'flight_quote': ('Get flight price in USD for an origin_id and destination_id.', {'origin_id':'string','destination_id':'string'}),
 'hotel_quote': ('Get total hotel price in USD for city_id and nights.', {'city_id':'string','nights':'integer'}),
 'weather': ('Get weather forecast for city_id.', {'city_id':'string'}),
 'finish_trip': ('Submit the requested total price in USD and destination weather after retrieving both quotes and weather.', {'total_usd':'integer','forecast':'string'}),
 'restaurant_search': ('Find restaurants in a city.', {'city_id':'string'}),
 'currency_rate': ('Get a currency exchange rate.', {'currency':'string'}),
 'cancel_booking': ('Cancel a booking.', {'booking_id':'string'})}
TOOLS = [{'type':'function','function':{'name':n,'description':d,'parameters':{'type':'object','properties':{k:{'type':v} for k,v in ps.items()},'required':list(ps),'additionalProperties':False}}} for n,(d,ps) in DESCRIPTIONS.items()]
SYSTEM = ('Complete the user travel request using tools. Resolve both city names to IDs, then retrieve flight and hotel quotes and destination weather. Submit their total and forecast with finish_trip. Use exact IDs returned by tools. Recover from tool errors when possible. Never invent tool outputs. Do not call unrelated tools. After successful submission, respond briefly.')
TEMPLATES = [
 'Get the flight price from {o} to {d}, the hotel price for {n} nights in {d}, and the weather in {d}. Submit the total in USD and forecast.',
 'For a trip from {o} to {d}, retrieve airfare, hotel cost for {n} nights, and destination weather. Submit total USD price and forecast.',
 'Check flights from {o} to {d}, accommodation for {n} nights in {d}, plus the weather forecast. Submit their total USD cost and forecast.',
 'Compare my travel expenses: flight from {o} to {d} and hotel for {n} nights in {d}. Also get destination weather; submit total USD and forecast.']

def digest(s): return int(hashlib.sha256(s.encode()).hexdigest()[:8],16)
def cid(city): return 'city_'+str(CITIES.index(city)+101)
def facts(o,d,n):
 return {'flight':80+digest(o+'>'+d)%700,'hotel':n*(40+digest(d)%160),'forecast':['sunny','rainy','cloudy'][digest(d)%3]}
def swap(word,rng):
 positions=[i for i in range(1,len(word)-1) if word[i]!=word[i+1]]
 if not positions: return word+'x'
 i=rng.choice(positions); return word[:i]+word[i+1]+word[i]+word[i+2:]
PARALLEL_SYSTEM = 'Retrieve the requested flight quote, hotel quote and destination weather with tools using city names. These lookups are independent and can all be called in one response. Do not invent outputs or call unrelated tools. Recover from errors if needed.'
PARALLEL_TEMPLATES = [
 'Get the flight price from {o} to {d}, the hotel price for {n} nights in {d}, and the weather forecast in {d}. Return these three lookup results.',
 'Retrieve airfare from {o} to {d}, accommodation cost for {n} nights in {d}, and destination weather. Return these three lookup results.'
]
def tools_for(row):
 names = {'flight_lookup','hotel_lookup','weather_lookup','restaurant_search','currency_rate','cancel_booking'} if row['suite']=='parallel' else set(DESCRIPTIONS)-{'flight_lookup','hotel_lookup','weather_lookup'}
 return [t for t in TOOLS if t['function']['name'] in names]
def dataset(n,seed,suites=('parallel','dependent')):
 rng=random.Random(seed); rows=[]
 for i in range(n):
  o,d=rng.sample(CITIES,2); nights=rng.randint(1,7)
  suite=suites[(i//2)%len(suites)]
  templates=PARALLEL_TEMPLATES if suite=='parallel' else TEMPLATES
  clean=templates[(i//4+i%2)%len(templates)].format(o=o,d=d,n=nights)
  category='intent' if i%2==0 else 'entity'
  if category=='entity':
   noisy=re.sub(r'\b'+re.escape(d)+r'\b',swap(d,rng),clean)
  else:
   candidates=[m for m in re.finditer(r'\b[A-Za-z]{5,}\b',clean) if m.group() not in CITIES and m.group().lower() not in {'submit'}]
   chosen=rng.sample(candidates,min(2,len(candidates))); noisy=clean
   for m in sorted(chosen,key=lambda m:m.start(),reverse=True): noisy=noisy[:m.start()]+swap(m.group(),rng)+noisy[m.end():]
  rows.append({'id':i,'suite':suite,'origin':o,'destination':d,'nights':nights,'clean':clean,'noisy':noisy,'category':category})
 return rows

def edit(a,b):
 # Optimal string alignment distance, character based, includes adjacent swaps.
 dp=[[0]*(len(b)+1) for _ in range(len(a)+1)]
 for i in range(len(a)+1): dp[i][0]=i
 for j in range(len(b)+1): dp[0][j]=j
 for i in range(1,len(a)+1):
  for j in range(1,len(b)+1):
   dp[i][j]=min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(a[i-1]!=b[j-1]))
   if i>1 and j>1 and a[i-1]==b[j-2] and a[i-2]==b[j-1]: dp[i][j]=min(dp[i][j],dp[i-2][j-2]+1)
 return dp[-1][-1]
# Deployment metadata only: no evaluation requests, gold arguments or answers.
VOCAB=collections.Counter(re.findall(r'[A-Za-z]+',' '.join(d for d,_ in DESCRIPTIONS.values())+' '+' '.join(CITIES)+' flight flights airfare hotel accommodation expenses travel destination nights forecast total price cost retrieve check compare sunny rainy cloudy'))
def term_correct(text):
 def fix(m):
  w=m.group(); low=w.lower(); vocab={v.lower():count for v,count in VOCAB.items()}
  if len(w)<4 or low in vocab: return w
  nearest=sorted((edit(low,v),-count,v) for v,count in vocab.items())
  if nearest[0][0]>1 or (len(nearest)>1 and nearest[1][0]==nearest[0][0]): return w
  v=nearest[0][2]
  return v.capitalize() if w[0].isupper() else v
 return re.sub(r'[A-Za-z]+',fix,text)

class Sandbox:
 def __init__(self,row): self.row=row; self.calls=[]; self.success=False; self.errors=0
 def execute(self,name,args):
  self.calls.append({'name':name,'arguments':args})
  try:
   if name not in DESCRIPTIONS: raise ValueError('Unknown tool')
   params=DESCRIPTIONS[name][1]
   if set(args)!=set(params): raise ValueError('Invalid argument keys')
   for k,t in params.items():
    if (t=='string' and not isinstance(args[k],str)) or (t=='integer' and (not isinstance(args[k],int) or isinstance(args[k],bool))): raise ValueError('Invalid argument type')
   def city(i):
    if i not in [cid(c) for c in CITIES]: raise ValueError('Unknown city_id')
    return CITIES[[cid(c) for c in CITIES].index(i)]
   def named_city(value):
    matched=[c for c in CITIES if c.lower()==value.lower()]
    if not matched: raise ValueError('City not found; retry spelling. Supported cities: '+', '.join(CITIES))
    return matched[0]
   if name in {'flight_lookup','hotel_lookup','weather_lookup'}:
    if name=='flight_lookup': result={'price_usd':facts(named_city(args['origin']),named_city(args['destination']),1)['flight']}
    elif name=='hotel_lookup':
     if args['nights']<1: raise ValueError('Nights must be positive')
     result={'price_usd':facts('Seoul',named_city(args['city']),args['nights'])['hotel']}
    else: result={'forecast':facts('Seoul',named_city(args['city']),1)['forecast']}
    if self.row['suite']=='parallel': self.success=all(any(canonical(x)==canonical(g) for x in self.calls) for g in gold_calls(self.row))
    return result
   if name=='resolve_city':
    matched=[c for c in CITIES if c.lower()==args['name'].lower()]
    if not matched: raise ValueError('City not found; retry spelling. Supported cities: '+', '.join(CITIES))
    return {'city_id':cid(matched[0])}
   if name=='flight_quote': return {'price_usd':facts(city(args['origin_id']),city(args['destination_id']),1)['flight']}
   if name=='hotel_quote':
    if args['nights']<1: raise ValueError('Nights must be positive')
    return {'price_usd':facts('Seoul',city(args['city_id']),args['nights'])['hotel']}
   if name=='weather': return {'forecast':facts('Seoul',city(args['city_id']),1)['forecast']}
   if name=='finish_trip':
    gold=gold_calls(self.row)
    previous=self.calls[:-1]
    required=gold[:-1]
    covered=all(any(canonical(x)==canonical(g) for x in previous) for g in required)
    f=facts(self.row['origin'],self.row['destination'],self.row['nights'])
    self.success=covered and args=={'total_usd':f['flight']+f['hotel'],'forecast':f['forecast']}
    # Validate completion without leaking any expected values.
    return {'submitted':True}
   return {'result':[]}
  except (ValueError,TypeError,KeyError) as e:
   self.errors+=1; return {'error':str(e)}

def canonical(c):
 args=dict(c['arguments'])
 keys=['name'] if c['name']=='resolve_city' else ['origin','destination','city'] if c['name'] in {'flight_lookup','hotel_lookup','weather_lookup'} else []
 for key in keys:
  if isinstance(args.get(key),str): args[key]=args[key].lower()
 return json.dumps([c['name'],args],sort_keys=True)
def gold_calls(r):
 o,d,n=r['origin'],r['destination'],r['nights']; f=facts(o,d,n)
 if r['suite']=='parallel': return [{'name':'flight_lookup','arguments':{'origin':o,'destination':d}},{'name':'hotel_lookup','arguments':{'city':d,'nights':n}},{'name':'weather_lookup','arguments':{'city':d}}]
 return [{'name':'resolve_city','arguments':{'name':o}},{'name':'resolve_city','arguments':{'name':d}}, {'name':'flight_quote','arguments':{'origin_id':cid(o),'destination_id':cid(d)}},{'name':'hotel_quote','arguments':{'city_id':cid(d),'nights':n}},{'name':'weather','arguments':{'city_id':cid(d)}},{'name':'finish_trip','arguments':{'total_usd':f['flight']+f['hotel'],'forecast':f['forecast']}}]

class API:
 def __init__(self,a): self.a=a; self.calls=0; self.tokens=0; self.seconds=0
 def call(self,messages,tools=None):
  payload={'model':self.a.model,'messages':messages,'reasoning_effort':self.a.effort,'max_completion_tokens':2048}
  if tools: payload.update(tools=tools,tool_choice='auto')
  started=time.perf_counter(); self.calls+=1
  # No silent fallback to another model or effort; failures remain visible.
  req=urllib.request.Request(self.a.base_url.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=90) as response: data=json.load(response)
   self.tokens+=data.get('usage',{}).get('total_tokens',0)
   return data['choices'][0]['message']
  finally: self.seconds+=time.perf_counter()-started

def scores(pred,gold):
 a=collections.Counter(canonical(c) for c in pred); b=collections.Counter(canonical(c) for c in gold)
 hit=sum((a&b).values()); p=hit/max(1,sum(a.values())); r=hit/sum(b.values())
 return {'call_multiset_exact':int(a==b),'argument_call_precision':p,'argument_call_recall':r,'argument_call_f1':2*p*r/(p+r) if p+r else 0}
def run_one(row,variant,a,mode="react"):
 api=API(a); sandbox=Sandbox(row); started=time.perf_counter(); correction_seconds=0; error=None; messages=[]
 text=row['clean'] if variant=='clean' else row['noisy']
 try:
  correction_started=time.perf_counter()
  if variant=='term': text=term_correct(text)
  if variant=='llm':
   msg=api.call([{'role':'system','content':'Correct spelling only. Preserve intent, entities, numbers, constraints and sentence structure. Do not add tool calls or answers. Return JSON with exactly one string field: text. Public deployment vocabulary: '+', '.join(sorted(VOCAB))},{'role':'user','content':text}])
   content=msg.get('content') or ''; content=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip())
   obj=json.loads(content)
   if set(obj)!={'text'} or not isinstance(obj['text'],str) or not obj['text'].strip(): raise ValueError('Invalid correction JSON')
   text=obj['text']
  correction_seconds=time.perf_counter()-correction_started
  messages=[{'role':'system','content':PARALLEL_SYSTEM if row['suite']=='parallel' else SYSTEM},{'role':'user','content':text}]
  for step in range(1 if mode=="one_shot" else a.max_steps):
   msg=api.call(messages,tools_for(row)); messages.append({k:v for k,v in msg.items() if k in {'role','content','tool_calls'}})
   calls=msg.get('tool_calls',[])
   if not calls: break
   for c in calls:
    try:
     arguments=json.loads(c['function']['arguments'])
     if not isinstance(arguments,dict): raise ValueError('Arguments must be object')
     result=sandbox.execute(c['function']['name'],arguments)
    except (ValueError,KeyError,TypeError) as e:
     sandbox.errors+=1; result={'error':str(e)}
    messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result)})
   if sandbox.success: break
 except Exception as e: error=type(e).__name__+': '+str(e)
 gold=gold_calls(row); ps={c['name'] for c in sandbox.calls}; gs={c['name'] for c in gold}
 p=len(ps&gs)/max(1,len(ps)); r=len(ps&gs)/len(gs)
 first=[]
 for m in messages:
  if m.get('role')=='assistant' and m.get('tool_calls'):
   for c in m['tool_calls']:
    try:
     parsed=json.loads(c['function']['arguments'])
     if isinstance(parsed,dict): first.append({'name':c['function']['name'],'arguments':parsed})
    except (KeyError,ValueError,TypeError): pass
   break
 first_scores=scores(first,gold if row['suite']=='parallel' else gold[:2])
 missing=[g for g in gold if not any(canonical(c)==canonical(g) for c in sandbox.calls)]
 failure_reason=None if sandbox.success and error is None else ('api_or_format_error' if error else 'no_tool_calls' if not sandbox.calls else 'missing_or_incorrect_required_calls' if missing else 'completion_not_validated')
 return {'id':row['id'],'category':row['category'],'variant':variant,'mode':mode,'suite':row['suite'],'severity':row.get('severity',1),'failure_reason':failure_reason,'missing_calls':missing,'first_step_call_f1':first_scores['argument_call_f1'],'first_step_call_exact':first_scores['call_multiset_exact'],'clean':row['clean'],'noisy':row['noisy'],'corrected':text,'correction_exact':int(text==row['clean']),'changed':int(text!=row['noisy']),'task_success':int(sandbox.success and error is None),'tool_set_exact':int(ps==gs),'tool_precision':p,'tool_recall':r,'tool_f1':2*p*r/(p+r) if p+r else 0,**scores(sandbox.calls,gold),'tool_errors':sandbox.errors,'tool_calls':len(sandbox.calls),'llm_calls':api.calls,'tokens':api.tokens,'correction_seconds':correction_seconds,'api_seconds':api.seconds,'wall_seconds':time.perf_counter()-started,'error':error,'trace':messages,'executed':sandbox.calls,'gold':gold}

def summarize(rows):
 out=[]
 metrics=['task_success','first_step_call_f1','first_step_call_exact','tool_set_exact','tool_precision','tool_recall','tool_f1','call_multiset_exact','argument_call_precision','argument_call_recall','argument_call_f1','correction_exact','changed','tool_errors','tool_calls','llm_calls','tokens','correction_seconds','wall_seconds']
 for suite,category in [(t,c) for t in ['all','parallel','dependent'] for c in ['all','intent','entity']]:
  for mode,variant in [(m,v) for m in ['one_shot','react'] for v in ['clean','raw','llm','term']]:
   subset=[r for r in rows if r['variant']==variant and r['mode']==mode and (suite=='all' or r['suite']==suite) and (category=='all' or r['category']==category)]
   if not subset: continue
   out.append({'suite':suite,'category':category,'mode':mode,'variant':variant,'n':len(subset),'api_or_format_errors':sum(r['error'] is not None for r in subset),**{k:statistics.mean(r[k] for r in subset) for k in metrics}})
 return out

def self_test():
 rows=dataset(100,42)
 assert rows==dataset(100,42) and all(r['clean']!=r['noisy'] for r in rows)
 for row in rows:
  s=Sandbox(row)
  for c in gold_calls(row): assert 'error' not in s.execute(c['name'],c['arguments'])
  assert s.success
  assert scores(s.calls,gold_calls(row))['call_multiset_exact']==1
  if row['suite']=='parallel': continue
  bad=Sandbox(row); bad.execute('finish_trip',gold_calls(row)[-1]['arguments']); assert not bad.success
  f=facts(row['origin'],row['destination'],row['nights'])
  bad=Sandbox(row)
  for c in gold_calls(row)[:-1]: bad.execute(c['name'],c['arguments'])
  bad.execute('finish_trip',{'total_usd':f['flight']+f['hotel']+1,'forecast':f['forecast']}); assert not bad.success
 assert edit('weather','waether')==1
 assert term_correct('waether in Tko yo')!='waether in Tko yo'
 print('PASS: 100 paired cases, executable oracle, dependency and wrong-total rejection, scoring, correction.')

def main():
 p=argparse.ArgumentParser(); p.add_argument('--model',default='gpt-6-luna'); p.add_argument('--effort',default='none'); p.add_argument('--n',type=int,default=100); p.add_argument('--seed',type=int,default=42); p.add_argument('--concurrency',type=int,default=4); p.add_argument('--max-steps',type=int,default=8); p.add_argument('--suites',nargs='+',choices=['parallel','dependent'],default=['parallel','dependent']); p.add_argument('--modes',nargs='+',choices=['one_shot','react'],default=['one_shot','react']); p.add_argument('--out',default='results'); p.add_argument('--base-url',default=os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1')); p.add_argument('--self-test',action='store_true'); p.add_argument('--prepare-only',action='store_true'); a=p.parse_args()
 if a.self_test: self_test(); return
 if a.n<1 or a.concurrency<1 or a.max_steps<1 or len(a.modes)!=len(set(a.modes)): p.error('n and concurrency must be positive')
 out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
 config=vars(a).copy(); config['benchmark_version']=BENCHMARK_VERSION; config.pop('self_test'); config.pop('prepare_only')
 cfg=out/'config.json'
 if cfg.exists() and json.loads(cfg.read_text())!=config: raise SystemExit('Config differs from checkpoint: use another --out directory.')
 cfg.write_text(json.dumps(config,indent=2))
 cases=dataset(a.n,a.seed,a.suites); (out/'cases.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in cases))
 if a.prepare_only: print('Prepared',len(cases),'cases; no API calls.'); return
 if not os.getenv('OPENAI_API_KEY'): raise SystemExit('Set OPENAI_API_KEY. No evaluation has run.')
 path=out/'predictions.jsonl'; rows=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
 seen={(r['id'],r['variant'],r['mode']) for r in rows}; jobs=[(r,v,m) for r in cases for v in ['clean','raw','llm','term'] for m in a.modes if (r['id'],v,m) not in seen]; random.Random(a.seed).shuffle(jobs)
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as pool, path.open('a') as f:
  pending=[pool.submit(run_one,r,v,a,m) for r,v,m in jobs]
  for future in concurrent.futures.as_completed(pending):
   row=future.result(); rows.append(row); f.write(json.dumps(row)+'\n'); f.flush(); print(f"{len(rows)}/{len(cases)*4*len(a.modes)} {row['mode']}/{row['variant']} success={row['task_success']} error={row['error']}",flush=True)
 summary=summarize(rows); (out/'summary.json').write_text(json.dumps(summary,indent=2))
 # Paired sample bootstrap: resample case IDs, preserving variant pairing.
 stats=[]
 comparisons=[(m,v,m,'raw') for m in a.modes for v in ['llm','term']]
 if set(a.modes)=={'react','one_shot'}: comparisons.extend(('react',v,'one_shot',v) for v in ['clean','raw','llm','term'])
 for mode,v,baseline_mode,baseline_variant in comparisons:
  left={r['id']:r for r in rows if r['mode']==mode and r['variant']==v}
  right={r['id']:r for r in rows if r['mode']==baseline_mode and r['variant']==baseline_variant}
  ids=sorted(left.keys() & right.keys())
  if not ids: continue
  delta=[left[i]['task_success']-right[i]['task_success'] for i in ids]; rng=random.Random(a.seed)
  boot=sorted(statistics.mean(rng.choices(delta,k=len(delta))) for _ in range(2000))
  stats.append({'mode':mode,'variant':v,'baseline_mode':baseline_mode,'baseline_variant':baseline_variant,'n':len(ids),'delta_task_success':statistics.mean(delta),'bootstrap_95_ci':[boot[49],boot[1949]],'rescued':sum(d==1 for d in delta),'regressed':sum(d==-1 for d in delta)})
 (out/'paired.json').write_text(json.dumps(stats,indent=2))
 lines=['| suite | category | mode | variant | n | success | first-step F1 | tool F1 | call exact | argument F1 | sec | errors |','|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for r in summary: lines.append(f"|{r['suite']}|{r['category']}|{r['mode']}|{r['variant']}|{r['n']}|{r['task_success']:.3f}|{r['first_step_call_f1']:.3f}|{r['tool_f1']:.3f}|{r['call_multiset_exact']:.3f}|{r['argument_call_f1']:.3f}|{r['wall_seconds']:.2f}|{r['api_or_format_errors']}|")
 (out/'summary.md').write_text('\n'.join(lines)+'\n'); print(out/'summary.md')
if __name__=='__main__': main()
