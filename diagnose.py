"""Inspect saved predictions from v2 or v3 without API calls."""
import argparse,json,collections
from pathlib import Path
import benchmark as b
p=argparse.ArgumentParser();p.add_argument('predictions');a=p.parse_args()
counts=collections.Counter()
for line in Path(a.predictions).read_text().splitlines():
 r=json.loads(line); gold=r['gold']; actual=r['executed']
 missing=[c for c in gold if not any(b.canonical(x)==b.canonical(c) for x in actual)]
 status=r.get('failure_reason') or ('success' if r['task_success'] else 'api_or_format_error' if r.get('error') else 'missing_or_incorrect_required_calls' if missing else 'completion_not_validated')
 counts[(r.get('suite','dependent_v2'),r['mode'],status)]+=1
 print(json.dumps({'id':r['id'],'variant':r['variant'],'mode':r['mode'],'suite':r.get('suite','dependent_v2'),'success':r['task_success'],'reason':status,'tool_errors':r['tool_errors'],'generated_calls':actual,'missing_calls':missing,'error':r.get('error')},ensure_ascii=False))
print('COUNTS')
for (suite,mode,reason),n in sorted(counts.items()):print(suite,mode,reason,n)
