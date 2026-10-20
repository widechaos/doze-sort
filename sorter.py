"""Plan content-based copies; leave every source file untouched."""
import argparse
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

MODEL='sentence-transformers/all-MiniLM-L6-v2'
REVISION='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
THRESHOLD=0.30
MARGIN=0.06


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('Symbolic links are not supported.')
    return path.resolve()


def roots(source, output):
    source=safe_path(source);output=safe_path(output)
    if not source.is_dir():raise ValueError('Input directory is missing.')
    if source==output or source in output.parents or output in source.parents:
        raise ValueError('Input and output directories must be separate, without nesting.')
    return source,output


def read_inbox(source):
    rows=[];skipped=[]
    entries=sorted(source.iterdir())
    if len(entries)>200:raise ValueError('Use a small inbox of at most 200 top-level entries.')
    for path in entries:
        if path.name.startswith('.') or path.suffix.lower() not in {'.md','.txt'}:
            skipped.append({'name':path.name,'reason':'Only visible top-level .md and .txt files are supported.'});continue
        if path.is_symlink() or not path.is_file():raise ValueError(f'{path.name}: expected a regular file, not a link or directory.')
        if path.stat().st_size>32768:raise ValueError(f'{path.name}: file exceeds 32 KiB.')
        data=path.read_bytes()
        if len(data)>32768:raise ValueError(f'{path.name}: file changed or exceeds the size limit.')
        try:text=data.decode('utf-8')
        except UnicodeError:raise ValueError(f'{path.name}: UTF-8 text required.')
        if not text.strip():raise ValueError(f'{path.name}: empty text.')
        rows.append({'name':path.name,'sha256':digest(data),'text':text,'data':data})
    if not rows:raise ValueError('No supported text files found.')
    return rows,skipped


class Planner:
    def __init__(self,cache=None):
        from sentence_transformers import SentenceTransformer
        self.model=SentenceTransformer(MODEL,revision=REVISION,device='cpu',cache_folder=cache or os.environ.get('DOZE_SORT_CACHE',str(Path.home()/'.cache/doze-sort')),trust_remote_code=False,local_files_only=os.environ.get('HF_HUB_OFFLINE')=='1')

    def plan(self,source,output,topics):
        source,output=roots(source,output)
        if not isinstance(topics,list) or not 2<=len(topics)<=12:raise ValueError('Provide 2–12 topics.')
        ids=[t.get('id') for t in topics]
        if any(not isinstance(t,str) or not re.fullmatch('[a-z][a-z0-9-]{0,30}',t) for t in ids) or len(set(ids))!=len(ids):raise ValueError('Topic IDs must be unique short lowercase slugs.')
        if any(not isinstance(t.get('description'),str) or not 10<=len(t['description'])<=600 for t in topics):raise ValueError('Topic descriptions must be 10–600 characters.')
        rows,skipped=read_inbox(source)
        texts=[t['description'] for t in topics]+[r['text'] for r in rows]
        tokens=self.model.tokenizer(texts,truncation=False)['input_ids']
        if any(len(x)>self.model.max_seq_length for x in tokens):raise ValueError('A file or topic exceeds the model token limit. Split it before sorting; no text is silently truncated.')
        vectors=self.model.encode(texts,normalize_embeddings=True,show_progress_bar=False)
        scores=vectors[len(topics):] @ vectors[:len(topics)].T
        records=[];seen={}
        for row,sim in zip(rows,scores):
            order=sorted(range(len(topics)),key=lambda i:-float(sim[i]));score=float(sim[order[0]]);gap=score-float(sim[order[1]])
            topic=ids[order[0]] if score>=THRESHOLD and gap>=MARGIN else '_review'
            duplicate=seen.get(row['sha256']);seen.setdefault(row['sha256'],row['name'])
            records.append({'name':row['name'],'sha256':row['sha256'],'topic':topic,'duplicate_of':duplicate,'score':round(score,4),'gap':round(gap,4),'suggestion':ids[order[0]],'reason':'Exact byte duplicate' if duplicate else ('Below score or separation threshold' if topic=='_review' else 'Content match'), 'excerpt':row['text'][:180]})
        return {'version':1,'id':uuid.uuid4().hex,'source':str(source),'output':str(output),'topics':topics,'files':records,'skipped':skipped,'model':MODEL,'revision':REVISION,'threshold':THRESHOLD,'margin':MARGIN}


def validate_plan(plan):
    if plan.get('version')!=1 or not re.fullmatch('[0-9a-f]{32}',str(plan.get('id'))):raise ValueError('Invalid plan identity.')
    source,output=roots(plan['source'],plan['output'])
    records=plan.get('files')
    if not isinstance(records,list) or not 1<=len(records)<=200:raise ValueError('Invalid plan files.')
    names=set();canonical={}
    for r in records:
        name=r['name']
        if not isinstance(name,str) or Path(name).name!=name or name in {'.','..'} or name.startswith('.') or '/' in name or '\\' in name or name in names:raise ValueError('Invalid or duplicate filename.')
        names.add(name)
        if not re.fullmatch('[0-9a-f]{64}',str(r['sha256'])) or not re.fullmatch('(?:[a-z][a-z0-9-]{0,30}|_review)',str(r['topic'])):raise ValueError('Invalid digest or topic.')
        if r['duplicate_of']:
            if canonical.get(r['duplicate_of'])!=r['sha256']:raise ValueError('Duplicate must reference an earlier identical file.')
        else:canonical[name]=r['sha256']
    current,skipped=read_inbox(source)
    if {(r['name'],r['sha256']) for r in current}!={(r['name'],r['sha256']) for r in records} or skipped!=plan['skipped']:
        raise ValueError('Inbox changed after planning. Create a fresh plan.')
    return source,output,{r['name']:r['data'] for r in current}


def apply(plan):
    source,output,bodies=validate_plan(plan)
    output.mkdir(parents=True,exist_ok=True)
    run=output/('run-'+plan['id']);recovered=output/('.undone-'+plan['id'])
    if run.exists() or recovered.exists():raise ValueError('This plan was already applied. No second copy was made.')
    # Stage a complete snapshot before exposing it as an active run.
    stage=output/('.stage-'+plan['id'])
    stage.mkdir()
    manifest={'id':plan['id'],'files':[],'duplicates':[]}
    for r in plan['files']:
        if r['duplicate_of']:
            manifest['duplicates'].append({'name':r['name'],'canonical':r['duplicate_of'],'sha256':r['sha256']});continue
        target=stage/r['topic']/r['name'];target.parent.mkdir(exist_ok=True)
        with target.open('xb') as f:f.write(bodies[r['name']])
        manifest['files'].append({'path':str(target.relative_to(stage)),'sha256':r['sha256']})
    with (stage/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2)
    stage.rename(run)
    return {'run':str(run),'copied':len(manifest['files']),'duplicates':len(manifest['duplicates']),'source_untouched':True}


def undo(output,plan_id):
    if not re.fullmatch('[0-9a-f]{32}',str(plan_id)):raise ValueError('Invalid run ID.')
    output=safe_path(output);run=output/('run-'+plan_id);recovery=output/('.undone-'+plan_id)
    if recovery.exists() and not run.exists():return {'state':'already undone','recovery':str(recovery)}
    safe_path(run)
    if not run.is_dir() or recovery.exists():raise ValueError('Active run is missing or recovery path exists.')
    manifest_file=run/'manifest.json'
    if manifest_file.is_symlink():raise ValueError('Manifest cannot be a symbolic link.')
    manifest=json.loads(manifest_file.read_text())
    expected={'manifest.json'}
    for item in manifest['files']:
        rel=Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid manifest path.')
        f=safe_path(run/rel)
        if run not in f.parents or not f.is_file() or digest(f.read_bytes())!=item['sha256']:raise ValueError('An output changed. Leave it in place and review manually.')
        expected.add(str(rel))
    actual=set()
    for f in run.rglob('*'):
        if f.is_symlink():raise ValueError('A link appeared in the output.')
        if f.is_file():actual.add(str(f.relative_to(run)))
    if actual!=expected:raise ValueError('Unexpected output files appeared. Nothing was moved.')
    run.rename(recovery)
    return {'state':'undone','recovery':str(recovery),'deleted_files':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Doze Sort: content-based copies, originals preserved')
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('source');p.add_argument('output');p.add_argument('--topics',default='topics.json');p.add_argument('--save',required=True)
    p=sub.add_parser('apply');p.add_argument('plan')
    p=sub.add_parser('undo');p.add_argument('output');p.add_argument('id')
    args=parser.parse_args()
    try:
        if args.action=='plan':
            result=Planner().plan(args.source,args.output,json.loads(Path(args.topics).read_text()))
            with Path(args.save).open('x') as f:json.dump(result,f,indent=2)
        elif args.action=='apply':result=apply(json.loads(Path(args.plan).read_text()))
        else:result=undo(args.output,args.id)
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,KeyError) as exc:parser.exit(1,str(exc)+'\n')
