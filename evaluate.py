"""Original fictional inbox diagnostic and actual copy/recovery exercise."""
import json
import statistics
import time
from pathlib import Path
from sorter import Planner,apply,undo,digest
ROOT=Path(__file__).parent
planner=Planner();topics=json.loads((ROOT/'topics.json').read_text());expected=json.loads((ROOT/'examples/expected.json').read_text());source=ROOT/'examples/inbox'
start=time.perf_counter();plan=planner.plan(source,ROOT/'.runtime/evaluation-output',topics);first=(time.perf_counter()-start)*1000
warm=[]
for _ in range(5):
    t=time.perf_counter();planner.plan(source,ROOT/'.runtime/evaluation-output',topics);warm.append((time.perf_counter()-t)*1000)
before={p.name:digest(p.read_bytes()) for p in source.iterdir()}
t=time.perf_counter();result=apply(plan);copy_ms=(time.perf_counter()-t)*1000
recovered=undo(ROOT/'.runtime/evaluation-output',plan['id']);after={p.name:digest(p.read_bytes()) for p in source.iterdir()}
cases=[{'name':r['name'],'expected':expected[r['name']],'actual':'duplicate' if r['duplicate_of'] else r['topic'],'score':r['score'],'gap':r['gap'],'suggestion':r['suggestion'],'duplicate_of':r['duplicate_of']} for r in plan['files']]
report={'purpose':'14 author-written fictional files; no independent benchmark or measured human time savings','model':plan['model'],'revision':plan['revision'],'threshold':plan['threshold'],'margin':plan['margin'],'cases':cases,'correct':sum(r['expected']==r['actual'] for r in cases),'total':len(cases),'copies':result['copied'],'duplicates':result['duplicates'],'review_copies':sum(r['topic']=='_review' and not r['duplicate_of'] for r in plan['files']),'sources_byte_identical':before==after,'undo_deleted_files':recovered['deleted_files'],'recovery_preserved':Path(recovered['recovery']).is_dir(),'first_plan_ms':round(first,2),'warm_plan_median_ms':round(statistics.median(warm),2),'apply_ms':round(copy_ms,2),'notes':'Timings exclude model loading. Score and margin thresholds are uncalibrated. Filename-only baseline has no category clues in note-N filenames. No comparison to a human filing session was conducted.'}
(ROOT/'docs/evaluation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
