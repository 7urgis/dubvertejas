#!/usr/bin/env python3
"""Local browser UI for Gemini subtitle imports and Japanese-reference dubbing."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

from dub_gemini import episode_files, export_package, output_directory, translation_file, FAST_OPTIONS
from dub_local import ROOT, dialogue_rows, import_translation, subtitle_rows
from dub_review import output_path, review_data, select_take, regeneration_request, rebuild_request

LOCK=threading.RLock()
JOB=dict(state='idle',episode=None,output=None,log=None)
PROCESS=None

PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini dubbing</title><style>
body{font:17px system-ui;background:#151922;color:#edf0f4;max-width:1200px;margin:32px auto;padding:16px}select,textarea,button{font:inherit;padding:10px;border-radius:5px}select,textarea{box-sizing:border-box;width:100%;background:#222936;color:inherit;border:1px solid #798599}textarea{height:430px;margin:8px 0;font:15px monospace}button{cursor:pointer;margin:10px 8px 10px 0}button:disabled{cursor:wait;opacity:.6}a{color:#9bd}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d1118;padding:16px;max-height:360px;overflow:auto}label{display:block;margin-top:20px}#message{min-height:28px}nav a{margin-right:18px}.subtitles{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:700px){.subtitles{grid-template-columns:1fr}}</style>
<h1>Gemini dubbing</h1><p>Extract the English subtitles already embedded in the video, copy them to Gemini, then paste the Lithuanian SRT with the same IDs and timestamps. Voices and rendering run locally.</p>
<label for="episode">Video in media/</label><select id="episode"></select>
<button id="retrieve">Extract embedded English subtitles</button><button id="refresh">Refresh videos</button>
<nav id="downloads" aria-label="Gemini translation files"></nav>
<div class="subtitles"><div><label for="english">Embedded English subtitles — full SRT</label>
<textarea id="english" readonly placeholder="Select a video and click Extract embedded English subtitles"></textarea>
<button id="copy">Copy English SRT</button></div><div>
<label for="translation">Gemini translation — SRT with original subtitle IDs and timestamps</label>
<textarea id="translation" placeholder="Paste the complete Lithuanian SRT translation here" spellcheck="false"></textarea>
</div></div>
<label><input id="fast" type="checkbox"> Fast variant: faster reference recognition, 24 voice steps, no speech check. Quality may differ.</label>
<button id="save">Save and validate</button><button id="start">Start dubbing</button>
<p id="message" role="status" aria-live="polite"></p>
<h2>Progress</h2><p id="state" role="status" aria-live="polite">Idle</p><p id="result"></p><pre id="log" aria-label="Dubbing log"></pre>
<script>
const $=id=>document.getElementById(id);
async function api(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await response.json();if(!response.ok)throw new Error(data.error);return data;}
function episode(){return Number($('episode').value);}
function links(files){$('downloads').replaceChildren();for(const file of files){const a=document.createElement('a');a.href='/download/'+episode()+'/'+file;a.textContent=file;a.download=file;$('downloads').append(a);}}
async function load(){const data=await api('/api/translation?episode='+episode());$('translation').value=data.text;$('english').value=data.english;links(data.files);}
async function scan(){const data=await api('/api/episodes');const old=$('episode').value;$('episode').replaceChildren();for(const item of data.episodes){const option=document.createElement('option');option.value=item.episode;option.textContent=String(item.episode).padStart(3,'0')+' — '+item.video;$('episode').append(option);}if([...$('episode').options].some(o=>o.value===old))$('episode').value=old;if(data.episodes.length)await load();else $('message').textContent='No original Dragon Ball Z LT-ENG-JAP MKV files found in media/.';}
async function action(button,path,body){button.disabled=true;try{const data=await api(path,body);$('message').textContent=data.message;if(data.files)links(data.files);if(data.english!==undefined)$('english').value=data.english;}catch(error){$('message').textContent=error.message;}finally{button.disabled=false;}}
$('episode').onchange=()=>load().catch(e=>$('message').textContent=e.message);
$('refresh').onclick=()=>scan().catch(e=>$('message').textContent=e.message);
$('retrieve').onclick=()=>action($('retrieve'),'/api/export',{episode:episode()});
$('copy').onclick=async()=>{if(!$('english').value){$('message').textContent='Extract the embedded subtitles first.';return;}try{await navigator.clipboard.writeText($('english').value);$('message').textContent='English SRT copied, including IDs and timestamps.';}catch(error){$('english').focus();$('english').select();$('message').textContent='Press Ctrl+C to copy the selected English SRT.';}};
$('save').onclick=()=>action($('save'),'/api/save',{episode:episode(),text:$('translation').value});
$('start').onclick=()=>action($('start'),'/api/start',{episode:episode(),text:$('translation').value,fast:$('fast').checked});
async function status(){try{const data=await api('/api/status');$('state').textContent=data.state+(data.episode?' — episode '+data.episode:'');$('log').textContent=data.log_text||'';$('start').disabled=data.state==='running';$('save').disabled=data.state==='running';$('result').replaceChildren();if(data.output){const a=document.createElement('a');a.href=data.output+'/index.html';a.textContent=data.state==='complete'?'Open completed video':'Output: '+data.output;if(data.state==='complete')$('result').append(a);}}catch(error){$('state').textContent='UI connection lost. '+error.message;}}
scan().catch(e=>$('message').textContent=e.message);status();setInterval(status,2000);
</script></html>'''


def save_translation(episode,text):
    if not isinstance(text,str) or not text.strip() or len(text.encode())>2_000_000:
        raise ValueError('Paste a nonempty SRT translation smaller than 2 MB')
    video,folder=episode_files(episode)
    export_package(video,folder,episode)
    source=subtitle_rows((folder/'english.srt').read_text(encoding='utf-8-sig'))
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.srt',dir=folder,delete=False) as file:
        file.write(text);candidate=Path(file.name)
    try:
        checked=import_translation(candidate,dialogue_rows(source),source)
        existing=[p for p in (folder/'translation.srt',folder/'translation.txt') if p.exists()]
        if len(existing)>1:raise ValueError('Keep only one of translation.srt or translation.txt in the episode folder')
        destination=existing[0] if existing else folder/'translation.srt'
        if destination.exists() and destination.read_bytes()!=candidate.read_bytes():
            history=folder/'history';history.mkdir(exist_ok=True)
            previous=destination.read_bytes();(history/(hashlib.sha256(previous).hexdigest()[:12]+'.srt')).write_bytes(previous)
        candidate.replace(destination)
    finally:
        candidate.unlink(missing_ok=True)
    return video,destination,len(checked)


def work(episode,log,fast=False,custom_command=None):
    global PROCESS
    state='failed';code=None
    try:
        with log.open('a') as stream:
            with LOCK:
                if JOB['state']!='running':return
                command=custom_command or ['unshare','-Urn',sys.executable,str(ROOT/'dub_gemini.py'),str(episode)]
                if fast and custom_command is None:command.append('--fast')
                PROCESS=subprocess.Popen(command,cwd=ROOT,
                    stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                process=PROCESS
            code=process.wait()
        state='complete' if code==0 else 'failed'
    except Exception as error:
        with log.open('a') as stream:stream.write(f'Failed to start dubbing: {error}\n')
    finally:
        with LOCK:
            PROCESS=None;JOB.update(state=state,returncode=code)


class Handler(BaseHTTPRequestHandler):
    def trusted(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        origin=self.headers.get('Origin')
        if self.headers.get('Host') not in allowed or (origin and origin not in {'http://'+host for host in allowed}):
            self.send_error(403,'This UI accepts local same-origin requests only');return False
        return True

    def reply(self,data,status=200):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)

    def html(self,text):
        payload=text.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)

    def file(self,path,download=False):
        if not path.is_file():self.send_error(404);return
        size=path.stat().st_size;start=0;end=size-1
        requested=self.headers.get('Range')
        if requested:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
            if not match:self.send_error(416);return
            start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
            if start>end:self.send_error(416);return
        self.send_response(206 if requested else 200)
        self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if download:self.send_header('Content-Disposition',f'attachment; filename="{path.name}"')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start);remaining=end-start+1
                while remaining:
                    chunk=stream.read(min(remaining,65536))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

    def do_GET(self):
        if not self.trusted():return
        route=urlparse(self.path)
        try:
            if route.path=='/':
                self.html(PAGE)
            elif route.path=='/review_editor.js':
                self.file(ROOT/'review_editor.js')
            elif route.path=='/api/review':
                name=parse_qs(route.query)['output'][0]
                self.reply(review_data(output_path(name)))
            elif route.path=='/api/episodes':
                episodes=[]
                for video in sorted((ROOT/'media').glob('Dragon.Ball.Z.*LT-ENG-JAP*.mkv')):
                    match=re.match(r'Dragon\.Ball\.Z\.(\d{3})\.',video.name)
                    if match:episodes.append(dict(episode=int(match[1]),video=video.name))
                self.reply(dict(episodes=episodes))
            elif route.path=='/api/translation':
                episode=int(parse_qs(route.query)['episode'][0]);_,folder=episode_files(episode)
                existing=[p for p in (folder/'translation.srt',folder/'translation.txt') if p.is_file()]
                self.reply(dict(text=existing[0].read_text(encoding='utf-8-sig') if len(existing)==1 else '',english=(folder/'english.srt').read_text(encoding='utf-8-sig') if (folder/'english.srt').is_file() else '',files=[name for name in ('english.srt','glossary.md','episode_context.md','prompt.txt') if (folder/name).is_file()]))
            elif route.path=='/api/status':
                with LOCK:state=dict(JOB)
                log=Path(state['log']) if state.get('log') else None
                if log and log.exists():
                    with log.open('rb') as stream:stream.seek(max(0,log.stat().st_size-32000));state['log_text']=stream.read().decode(errors='replace')
                self.reply(state)
            elif route.path.startswith('/download/'):
                _,_,episode,name=route.path.split('/')
                if name not in ('english.srt','glossary.md','episode_context.md','prompt.txt'):raise ValueError('Unknown download')
                _,folder=episode_files(int(episode));self.file(folder/name,download=True)
            elif route.path.startswith('/output/gemini/'):
                path=(ROOT/unquote(route.path).lstrip('/')).resolve()
                if not path.is_relative_to((ROOT/'output/gemini').resolve()):raise ValueError('Invalid output path')
                if path.name=='index.html' and (path.parent/'settings.json').is_file() and (path.parent/'transcript.json').is_file():
                    self.html(path.read_text()+'\n<script src="/review_editor.js" defer></script>')
                else:self.file(path)
            else:self.send_error(404)
        except (ValueError,KeyError,OSError,subprocess.SubprocessError) as error:self.reply(dict(error=str(error)),400)

    def do_POST(self):
        if not self.trusted():return
        try:
            if self.headers.get('Content-Type')!='application/json':raise ValueError('Expected application/json')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2_000_000:raise ValueError('Request is empty or larger than 2 MB')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError('Expected a JSON object')
            with LOCK:
                if JOB['state']=='running':self.reply(dict(error='A dubbing job is already running. Wait for it to finish.'),409);return
                if self.path in ('/api/review/regenerate','/api/review/select','/api/review/rebuild'):
                    name=data.get('output');out=output_path(name)
                    if self.path=='/api/review/select':
                        select_take(out,data.get('idx'),data.get('take'))
                        self.reply(dict(message='Take selected. Rebuild the video to apply your choices.'));return
                    if self.path=='/api/review/regenerate':
                        request=regeneration_request(out,data.get('idx'),data.get('text'));destination=out;kind='regenerate'
                    else:request,destination=rebuild_request(out);kind='rebuild'
                    logs=ROOT/'output/gemini_ui_logs';logs.mkdir(parents=True,exist_ok=True);log=logs/(request.parent.name+'.log')
                    command=['unshare','-Urn',sys.executable,str(ROOT/'dub_review.py'),'--request',str(request)]
                    episode=int(name.split('/')[0])
                    JOB.update(state='running',episode=episode,output='/'+str(destination.relative_to(ROOT)),log=str(log),returncode=None,
                        kind=kind,review_output=name,idx=data.get('idx'))
                    threading.Thread(target=work,args=(episode,log,False,command),daemon=True).start()
                    self.reply(dict(message='Generating a new take…' if kind=='regenerate' else 'Rebuilding a separate video…'));return
                episode=data['episode']
                if type(episode) is not int:raise ValueError('Episode must be an integer')
                if self.path=='/api/export':
                    video,folder=episode_files(episode);export_package(video,folder,episode)
                    self.reply(dict(message='Embedded English subtitles extracted. Copy the full SRT on the left into Gemini.',english=(folder/'english.srt').read_text(encoding='utf-8-sig'),files=[name for name in ('english.srt','glossary.md','episode_context.md','prompt.txt') if (folder/name).is_file()]));return
                if self.path not in ('/api/save','/api/start'):self.send_error(404);return
                video,translation,count=save_translation(episode,data.get('text'))
                if self.path=='/api/save':self.reply(dict(message=f'Saved and validated {count} dialogue cues: {translation}'));return
                fast=data.get('fast',False)
                if type(fast) is not bool:raise ValueError('Fast variant must be true or false')
                out=output_directory(episode,video,translation,options=FAST_OPTIONS if fast else None)
                logs=ROOT/'output/gemini_ui_logs';logs.mkdir(parents=True,exist_ok=True);log=logs/f'{episode:03d}-{out.name}.log'
                JOB.update(state='running',episode=episode,output='/'+str(out.relative_to(ROOT)),log=str(log),returncode=None,kind='dub',review_output=None,idx=None)
                threading.Thread(target=work,args=(episode,log,fast),daemon=True).start()
                self.reply(dict(message=f'Started episode {episode:03d} with {count} Gemini dialogue cues.'))
        except (ValueError,KeyError,OSError,subprocess.SubprocessError) as error:self.reply(dict(error=str(error)),400)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Open http://127.0.0.1:{server.server_port} — closing this server stops its active dubbing job; completed checkpoints remain.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        with LOCK:
            JOB['state']='stopped'
            if PROCESS and PROCESS.poll() is None:
                os.killpg(PROCESS.pid,signal.SIGTERM)
        server.server_close()


if __name__=='__main__':main()
