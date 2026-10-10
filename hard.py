#!/usr/bin/env python3
"""Hard independent multi-tool ablation; reuse API, runner, metrics, checkpointing."""
import collections, datetime, json, random, re
import benchmark as b

b.BENCHMARK_VERSION='hard-v1'
b.CITIES[:]=['Seoul','Tokyo','Osaka','Busan','Paris','Paros','London','Berlin','Madrid','Rome','Sydney','Lyon','Leon','Milan','Miami','Austin','Boston','Bergen','Bremen','Dublin']
CATALOG={
 'flight_price':('Look up airfare only, not seat availability or reservations.', {'origin':'string','destination':'string','date':'string','passengers':'integer','cabin':'string'}),
 'flight_seats':('Look up seat availability only, not prices or reservations.', {'origin':'string','destination':'string','date':'string','passengers':'integer','cabin':'string'}),
 'flight_reserve':('Reserve flight seats. Use only when booking is explicitly requested.', {'origin':'string','destination':'string','date':'string','passengers':'integer','cabin':'string'}),
 'hotel_price':('Look up total hotel cost only, not vacancies or booking.', {'city':'string','checkin':'string','nights':'integer','rooms':'integer','refundable':'boolean'}),
 'hotel_vacancies':('Look up hotel vacancies only, not prices or booking.', {'city':'string','checkin':'string','nights':'integer','rooms':'integer','refundable':'boolean'}),
 'hotel_reserve':('Reserve hotel rooms only if explicitly requested.', {'city':'string','checkin':'string','nights':'integer','rooms':'integer','refundable':'boolean'}),
 'weather_forecast':('Get predicted weather on a future date, not past weather or warnings.', {'city':'string','date':'string','unit':'string'}),
 'weather_history':('Get recorded weather on a past date, not forecasts or warnings.', {'city':'string','date':'string','unit':'string'}),
 'weather_alerts':('Get weather warnings on a date, not a weather forecast or historic records.', {'city':'string','date':'string','unit':'string'}),
 'rail_price':('Look up train fares only, not duration or tickets.', {'origin':'string','destination':'string','date':'string','passengers':'integer'}),
 'rail_duration':('Look up train travel duration only, not fares or tickets.', {'origin':'string','destination':'string','date':'string','passengers':'integer'}),
 'rail_reserve':('Reserve train tickets only if explicitly requested.', {'origin':'string','destination':'string','date':'string','passengers':'integer'}),
 'restaurant_menu':('Get restaurant menus, not table availability or reservations.', {'city':'string','date':'string','guests':'integer'}),
 'restaurant_tables':('Check restaurant table availability, not menus or booking.', {'city':'string','date':'string','guests':'integer'}),
 'restaurant_reserve':('Reserve restaurant tables only if explicitly requested.', {'city':'string','date':'string','guests':'integer'}),
}
# Metadata is public deployment information, shared by term and LLM correction.
PUBLIC='price seats reserve vacancies forecast history alerts duration menu tables refundable nonrefundable economy business celsius fahrenheit passengers rooms guests flight hotel rail train weather restaurant lookup cost fares availability predicted recorded future past return outbound exclude cancelled replacement instead itinerary'
b.VOCAB=collections.Counter(re.findall('[A-Za-z]+',' '.join(d for d,_ in CATALOG.values())+' '+' '.join(b.CITIES)+' '+PUBLIC))
b.DESCRIPTIONS.update(CATALOG)
def schema(name,d,ps):
 props={k:{'type':v} for k,v in ps.items()}
 for k,values in {'cabin':['economy','business'],'unit':['celsius','fahrenheit']}.items():
  if k in props:props[k]['enum']=values
 return {'type':'function','function':{'name':name,'description':d,'parameters':{'type':'object','properties':props,'required':list(ps),'additionalProperties':False}}}
MENU=[schema(n,d,ps) for n,(d,ps) in CATALOG.items()]
b.PARALLEL_SYSTEM='Execute exactly the requested independent lookups with tools. Use the final corrected itinerary, honor exclusions, distinguish prices, availability, forecasts, history and reservations. Resolve dates, counts, direction, units and constraints from the user request. All requested arguments are available in the request; multiple calls may be generated together. Do not execute explicitly excluded actions. Do not invent results.'
b.SYSTEM=b.PARALLEL_SYSTEM
b.tools_for=lambda row: row['menu']

def corrupt(word,rng,edits):
 value=word
 for _ in range(edits):
  if len(value)<4:break
  kind=rng.choice(['transpose','delete','replace'])
  i=rng.randrange(1,len(value)-1)
  if kind=='transpose':value=value[:i]+value[i+1]+value[i]+value[i+2:]
  elif kind=='delete':value=value[:i]+value[i+1:]
  else:value=value[:i]+rng.choice('abcdefghijklmnopqrstuvwxyz')+value[i+1:]
 if value==word:value=b.swap(word,rng)
 return value

def dataset(n,seed,suites=('parallel',)):
 if any(s!='parallel' for s in suites): raise SystemExit('Hard benchmark supports parallel tasks only: pass --suites parallel. Dependent tasks remain in benchmark.py.')
 rng=random.Random(seed);rows=[]
 for i in range(n):
  origin,first,second,cancelled=rng.sample(b.CITIES,4)
  date1=(datetime.date(2026,11,1)+datetime.timedelta(days=rng.randrange(20))).isoformat()
  date2=(datetime.date.fromisoformat(date1)+datetime.timedelta(days=rng.randint(3,8))).isoformat()
  past=(datetime.date(2026,8,1)+datetime.timedelta(days=rng.randrange(20))).isoformat()
  pax=rng.randint(1,5);rooms=rng.randint(1,3);n1=rng.randint(1,5);n2=rng.randint(1,5)
  cabin=rng.choice(['economy','business']);unit=rng.choice(['celsius','fahrenheit']);refund=rng.choice([True,False])
  flight=rng.choice(['flight_price','flight_seats']); hotel=rng.choice(['hotel_price','hotel_vacancies']);rail=rng.choice(['rail_price','rail_duration']);food=rng.choice(['restaurant_menu','restaurant_tables'])
  gold=[{'name':flight,'arguments':{'origin':origin,'destination':first,'date':date1,'passengers':pax,'cabin':cabin}},
   {'name':flight,'arguments':{'origin':first,'destination':second,'date':date2,'passengers':pax,'cabin':cabin}},
   {'name':hotel,'arguments':{'city':first,'checkin':date1,'nights':n1,'rooms':rooms,'refundable':refund}},
   {'name':hotel,'arguments':{'city':second,'checkin':date2,'nights':n2,'rooms':rooms,'refundable':not refund}},
   {'name':'weather_forecast','arguments':{'city':first,'date':date1,'unit':unit}},
   {'name':'weather_history','arguments':{'city':second,'date':past,'unit':unit}},
   {'name':rail,'arguments':{'origin':second,'destination':origin,'date':date2,'passengers':pax}},
   {'name':food,'arguments':{'city':second,'date':date2,'guests':pax}}]
  fphrase='airfare prices' if flight=='flight_price' else 'flight seat availability'
  hphrase='hotel prices' if hotel=='hotel_price' else 'hotel vacancies'
  rphrase='train fares' if rail=='rail_price' else 'train travel duration'
  foodphrase='restaurant menus' if food=='restaurant_menu' else 'restaurant table availability'
  # Natural language contains a cancelled plan and explicit scope exclusions.
  clean=(f'Old plan was {origin} to {cancelled} with 1 passenger and 1 room; that plan is cancelled. Final itinerary: {origin} to {first} on {date1}, then {first} to {second} on {date2}. '
   f'For both flight legs check {fphrase}, for {pax} passengers in {cabin}; do not reserve seats. '
   f'Check {hphrase} for {rooms} rooms: {n1} nights in {first} starting {date1} with refundable={str(refund).lower()}, and {n2} nights in {second} starting {date2} with refundable={str(not refund).lower()}. Do not reserve rooms. '
   f'Get predicted weather in {first} on {date1} and recorded weather in {second} on {past}, both in {unit}; no weather alerts. '
   f'Check {rphrase} from {second} back to {origin} on {date2} for the same passengers; no train booking. '
   f'Get {foodphrase} in {second} on {date2} for {pax} guests, without reserving tables. Ignore the cancelled city entirely.')
  category='intent' if i%2==0 else 'entity';severity=1+(i//2)%2
  if category=='entity':
   mapping={c:corrupt(c,rng,severity) for c in [first,second]}
   noisy=re.sub(r'\b(?:'+ '|'.join(map(re.escape,mapping))+r')\b',lambda m:mapping[m.group()],clean)
  else:
   candidates=[m for m in re.finditer(r'\b[A-Za-z]{5,}\b',clean) if m.group() not in b.CITIES and m.group().lower() not in {'false','true','ignore','cancelled','refundable','nonrefundable'}]
   noisy=clean
   for m in sorted(rng.sample(candidates,min(6,len(candidates))),key=lambda m:m.start(),reverse=True):noisy=noisy[:m.start()]+corrupt(m.group(),rng,severity)+noisy[m.end():]
  menu=list(MENU);rng.shuffle(menu)
  rows.append({'id':i,'suite':'parallel','category':category,'origin':origin,'destination':first,'nights':n1,'clean':clean,'noisy':noisy,'severity':severity,'gold_calls':gold,'menu':menu})
 return rows
b.dataset=dataset
b.gold_calls=lambda row:row['gold_calls']

class Sandbox:
 def __init__(self,row):self.row=row;self.calls=[];self.success=False;self.errors=0;self.valid_calls=[]
 def execute(self,name,args):
  self.calls.append({'name':name,'arguments':args})
  try:
   if name not in CATALOG:raise ValueError('Unknown tool')
   ps=CATALOG[name][1]
   if set(ps)!=set(args):raise ValueError('Invalid argument keys')
   for k,t in ps.items():
    if type(args[k])!={'string':str,'integer':int,'boolean':bool}[t]:raise ValueError('Invalid type: '+k)
    if t=='integer' and args[k]<1:raise ValueError('Counts must be positive')
    if k in {'origin','destination','city'} and args[k].lower() not in [c.lower() for c in b.CITIES]:raise ValueError('City not found; retry spelling')
    if k in {'date','checkin'}:datetime.date.fromisoformat(args[k])
   if 'cabin' in args and args['cabin'] not in {'economy','business'}:raise ValueError('Invalid cabin')
   if 'unit' in args and args['unit'] not in {'celsius','fahrenheit'}:raise ValueError('Invalid unit')
   self.valid_calls.append({'name':name,'arguments':dict(args)})
   self.success=all(any(b.canonical(c)==b.canonical(g) for c in self.valid_calls) for g in b.gold_calls(self.row)) and all(c['name'] in {g['name'] for g in b.gold_calls(self.row)} for c in self.calls)
   value=b.digest(name+json.dumps(args,sort_keys=True))%1000
   return {'result':value,'kind':name}
  except (ValueError,TypeError,KeyError) as e:self.errors+=1;return {'error':str(e)}
b.Sandbox=Sandbox
# All named city fields are case insensitive.
old_canonical=b.canonical
def canonical(c):
 args=c['arguments'].copy()
 for k in ['origin','destination','city']:
  if isinstance(args.get(k),str):args[k]=args[k].lower()
 return json.dumps([c['name'],args],sort_keys=True)
b.canonical=canonical

if __name__=='__main__':
 import sys
 if '--suites' not in sys.argv:sys.argv.extend(['--suites','parallel'])
 if '--self-test' in sys.argv:
  from test_hard import check
  check()
 else:b.main()
