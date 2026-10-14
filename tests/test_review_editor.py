"""Run: tools/Applio/.venv/bin/python tests/test_review_editor.py"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import urllib.error
import urllib.request
from unittest.mock import patch

import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dub_review as review
import gemini_ui as ui
from dub_local import save_json

class Model:
    sampling_rate=24000
    @classmethod
    def from_pretrained(cls,*args,**kwargs):return cls()
    def create_voice_clone_prompt(self,**kwargs):return kwargs
    def generate(self,**kwargs):
        assert kwargs['text']==['Pakeistas tekstas.'] and kwargs['num_step']==24
        return [np.full(12000,.2,dtype='float32')]
torch=SimpleNamespace(float16='float16',manual_seed=lambda seed:None,cuda=SimpleNamespace(OutOfMemoryError=RuntimeError,empty_cache=lambda:None))

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);out=root/'output/gemini/068/test';out.mkdir(parents=True)
    (root/'media').mkdir();video=root/'media/test.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=32x32:rate=25:duration=3','-c:v','mpeg4',str(video)],check=True)
    (root/'tests').mkdir();runner=Path(__file__).with_name('japanese_cast_episode.py')
    (root/'tests/japanese_cast_episode.py').write_bytes(runner.read_bytes())
    (root/'review_editor.js').write_bytes(Path('review_editor.js').read_bytes())
    refs=out/'references';refs.mkdir();ref=refs/'line_001.wav';sf.write(ref,np.full(24000,.1),24000)
    generated=out/'generated';generated.mkdir()
    sf.write(generated/'line_001.wav',np.full(12000,.15),24000)
    sf.write(generated/'line_002.wav',np.full(12000,.1),24000)
    rows=[dict(idx=i,lt='Pradinis tekstas.',en='Original.',start_sec=i-1,end_sec=i-.5,source_ids=[i],speaker='Test',reference=str(ref),reference_text='Japanese',reference_anchor_idx=i) for i in (1,2)]
    save_json(out/'transcript.json',rows);save_json(out/'settings.json',dict(video=str(video),steps=24,batch_size=1,speech_check_skipped=True))
    save_json(out/'generation.json',{str(i):dict(sha256=hashlib.sha256((generated/f'line_{i:03d}.wav').read_bytes()).hexdigest()) for i in (1,2)})
    (out/'index.html').write_text('<html><table></table></html>')
    sr=44100;t=np.arange(sr*3)/sr;audio=np.column_stack([.15*np.sin(t*2*np.pi*300)]*2).astype('float32')
    sf.write(out/'japanese.wav',audio,sr,subtype='FLOAT')
    stem=out/'separated/htdemucs/japanese/no_vocals.wav';stem.parent.mkdir(parents=True);sf.write(stem,audio*.2,sr,subtype='FLOAT')
    original={p:p.read_bytes() for p in (out/'transcript.json',out/'settings.json',out/'index.html',*generated.glob('*.wav'))}
    with patch.object(review,'ROOT',root),patch.object(ui,'ROOT',root):
        assert review.output_path('068/test')==out
        for name in ('068/../test','../068/test','068/test/review','068/../../media','068/missing'):
            try:review.output_path(name)
            except ValueError:pass
            else:raise AssertionError('Invalid output path accepted')
        for idx,text in ((True,'Valid'),(9,'Valid'),(1,''),(1,'x'*1001),(1,'Bad\x00text')):
            try:review.regeneration_request(out,idx,text)
            except ValueError:pass
            else:raise AssertionError('Invalid line/text accepted')
        request=review.regeneration_request(out,1,'Pakeistas tekstas.')
        with patch.dict(sys.modules,{'torch':torch,'omnivoice':SimpleNamespace(OmniVoice=Model)}):review.run_request(request)
        token=request.parent.name;data=review.review_data(out)
        assert not data['dirty'] and data['rows'][0]['takes'][0]['text']=='Pakeistas tekstas.'
        for idx,take in ((2,token),(1,'../escape')):
            try:review.select_take(out,idx,take)
            except ValueError:pass
            else:raise AssertionError('Wrong line or unsafe take accepted')
        review.select_take(out,1,token)
        build,destination=review.rebuild_request(out)
        review.select_take(out,1,'original')
        assert not review.review_data(out)['dirty']
        # Rebuild uses the frozen selection even if later choices change.
        review.run_request(build)
        changed=json.loads((destination/'transcript.json').read_text())
        assert changed[0]['lt']=='Pakeistas tekstas.' and changed[1]['lt']=='Pradinis tekstas.'
        assert (destination/'generated/line_002.wav').read_bytes()==(generated/'line_002.wav').read_bytes()
        assert (destination/'generated/line_001.wav').read_bytes()==(request.parent/'generated/line_001.wav').read_bytes()
        assert all(p.read_bytes()==content for p,content in original.items()), 'Accepted source was overwritten'
        assert review.review_data(out)['renders']==[destination.relative_to(root/'output/gemini').as_posix()]
        for idx in (1,2):review.select_take(out,idx,'japanese')
        japanese_request,japanese=review.rebuild_request(out)
        review.run_request(japanese_request)
        background,_=sf.read(japanese/'background.flac')
        ai,_=sf.read(japanese/'ai_voice.flac')
        assert np.max(np.abs(background-audio))<.0001 and not np.any(ai)
        assert all(r['keep_japanese'] for r in json.loads((japanese/'transcript.json').read_text()))
        assert all(r['selected']=='japanese' for r in review.review_data(japanese)['rows'])
        assert 'Pradinis tekstas.' not in (japanese/'transcript.vtt').read_text()
        assert 'generated/line_001.wav' in (japanese/'index.html').read_text(), 'Japanese lines lost their edit controls'
        review.select_take(japanese,1,'original')
        restore_request,restored=review.rebuild_request(japanese)
        review.run_request(restore_request)
        restored_rows=json.loads((restored/'transcript.json').read_text())
        assert not restored_rows[0]['keep_japanese'] and restored_rows[1]['keep_japanese']
        ai,aisr=sf.read(restored/'ai_voice.flac');background,_=sf.read(restored/'background.flac')
        assert np.any(ai[:aisr//2]) and not np.any(ai[aisr:])
        assert np.max(np.abs(background[sr:3*sr//2]-audio[sr:3*sr//2]))<.0001
        for idx in (1,2):review.select_take(out,idx,'original')
        assert all(p.read_bytes()==content for p,content in original.items())
        server=ui.ThreadingHTTPServer(('127.0.0.1',0),ui.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        def post(path,body,origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            request=urllib.request.Request(url+path,data=json.dumps(body).encode(),headers=headers)
            with urllib.request.urlopen(request) as response:return json.load(response)
        try:
            with urllib.request.urlopen(url+'/output/gemini/068/test/index.html') as response:assert b'/review_editor.js' in response.read()
            with urllib.request.urlopen(url+'/api/review?output=068/test') as response:assert len(json.load(response)['rows'])==2
            assert 'selected' in post('/api/review/select',dict(output='068/test',idx=1,take=token))['message']
            try:post('/api/review/select',dict(output='068/test',idx=1,take='original'),origin='http://evil.example')
            except urllib.error.HTTPError as error:assert error.code==403
            else:raise AssertionError('Cross-origin editing accepted')
            with patch.object(ui,'work') as work:
                post('/api/review/regenerate',dict(output='068/test',idx=1,text='Pakeistas tekstas.'))
                for _ in range(10):
                    if work.called:break
                    threading.Event().wait(.01)
                assert work.call_args.args[3][3].endswith('dub_review.py')
                assert ui.JOB['kind']=='regenerate' and ui.JOB['idx']==1
                try:post('/api/review/regenerate',dict(output='068/test',idx=1,text='Another'))
                except urllib.error.HTTPError as error:assert error.code==409
                else:raise AssertionError('Concurrent GPU jobs accepted')
        finally:
            ui.JOB.update(state='idle');server.shutdown();server.server_close();thread.join()
print('Review editing, alternate takes, frozen rebuild, preservation and HTTP checks passed')
