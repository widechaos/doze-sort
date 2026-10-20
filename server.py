"""Fixed fictional-inbox demo. Arbitrary paths are available only through the CLI."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from sorter import Planner,apply,undo
ROOT=Path(__file__).parent
PORT=8799
class Demo:
    def __init__(self):
        self.planner=Planner();self.plan=None;self.result=None;self.phase='ready';self.elapsed=None
    def state(self):
        return {'phase':self.phase,'files':self.plan['files'] if self.plan else [],'elapsed_ms':self.elapsed,'result':({k:v for k,v in self.result.items() if k not in {'run','recovery'}} if self.result else None),'run_name':Path(self.result.get('run',self.result.get('recovery',''))).name if self.result else None}
    def act(self,action):
        if action=='plan':
            if self.phase=='applied':raise ValueError('Undo the active demo before making another plan.')
            start=time.perf_counter();self.plan=self.planner.plan(ROOT/'examples/inbox',ROOT/'.runtime/output',json.loads((ROOT/'topics.json').read_text()));self.elapsed=round((time.perf_counter()-start)*1000,2);self.result=None;self.phase='planned'
        elif action=='apply':
            if self.phase!='planned':raise ValueError('Create and review a new plan first.')
            self.result=apply(self.plan);self.phase='applied'
        elif action=='undo':
            if self.phase!='applied':raise ValueError('There is no active demo run to undo.')
            self.result=undo(ROOT/'.runtime/output',self.plan['id']);self.phase='undone'
        else:raise ValueError('Unknown action.')
        return self.state()

if __name__=='__main__':
    demo=Demo();lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body,kind='application/json'):
            data=body if isinstance(body,bytes) else json.dumps(body).encode();self.send_response(status)
            for key,value in {'Content-Type':kind,'Content-Length':str(len(data)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(data)
        def host_ok(self):return self.headers.get('Host') in {f'127.0.0.1:{PORT}',f'localhost:{PORT}'}
        def do_GET(self):
            if not self.host_ok():return self.reply(403,{'error':'Local host required.'})
            if self.path=='/api/state':
                with lock:return self.reply(200,demo.state())
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
            if self.path not in files:return self.reply(404,{'error':'Not found.'})
            name,kind=files[self.path];self.reply(200,(ROOT/'web'/name).read_bytes(),kind)
        def do_POST(self):
            if not self.host_ok() or self.headers.get('Origin') not in {f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}:return self.reply(403,{'error':'Local browser origin required.'})
            if self.path not in {'/api/plan','/api/apply','/api/undo'}:return self.reply(404,{'error':'Unknown operation.'})
            try:
                if self.headers.get('Content-Type')!='application/json' or int(self.headers.get('Content-Length','0'))!=2 or self.rfile.read(2)!=b'{}':return self.reply(400,{'error':'The demo accepts only an empty JSON object, not paths or files.'})
                with lock:result=demo.act(self.path.split('/')[-1])
                self.reply(200,result)
            except (ValueError,OSError,KeyError) as exc:self.reply(400,{'error':str(exc)})
    print(f'Doze Sort demo: http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
