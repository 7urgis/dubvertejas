"""Run: tools/Applio/.venv/bin/python tests/test_fast_dub.py"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dub_gemini as gemini
from dub_local import FAST_OPTIONS
spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('japanese_cast_episode.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class OutOfMemoryError(RuntimeError):pass
calls=[];loads=[];oom=False
class Model:
    sampling_rate=24000
    @classmethod
    def from_pretrained(cls,*args,**kwargs):loads.append(1);return cls()
    def create_voice_clone_prompt(self,ref_audio,ref_text):return (ref_audio,ref_text)
    def generate(self,**kwargs):
        global oom
        calls.append(kwargs)
        assert sys.exc_info()[0] is None, 'OOM retry retains exception traceback'
        if oom and len(kwargs['text'])>1:
            oom=False;raise OutOfMemoryError('test batch too large')
        return [np.full(6000,.1*(int(text[-1])),dtype='float32') for text in kwargs['text']]

torch=SimpleNamespace(float16='float16',manual_seed=Mock(),cuda=SimpleNamespace(OutOfMemoryError=OutOfMemoryError,empty_cache=Mock()))
with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,{'torch':torch,'omnivoice':SimpleNamespace(OmniVoice=Model)}):
    root=Path(directory);out=root/'voices';out.mkdir();runner.OUT=out
    rows=[dict(idx=i,lt=f'Text {i}',reference=f'ref{i}.wav',reference_text=f'Japanese {i}',speaker=f'Actor {i}') for i in (1,2,3)]
    runner.generate(rows,set(),24,2)
    assert [len(c['text']) for c in calls]==[2,1]
    assert all(c['num_step']==24 for c in calls)
    assert calls[0]['voice_clone_prompt']==[('ref1.wav','Japanese 1'),('ref2.wav','Japanese 2')]
    saved=json.loads((out/'generation.json').read_text())
    assert saved['1']['batch_ids']==[1,2] and saved['3']['batch_ids']==[3]
    for i in (1,2,3):
        audio,sr=sf.read(out/f'generated/line_{i:03d}.wav')
        assert abs(audio[0]-.1*i)<.0001 and sr==24000
    runner.generate(rows,set(),24,2)
    assert len(loads)==1 and len(calls)==2, 'Cache reuse still loads the model'
    assert runner.fingerprint(rows[0],24,2)!=runner.fingerprint(rows[0],16,2)
    assert runner.fingerprint(rows[0],24,2)!=runner.fingerprint(rows[0],24,1)
    oom=True;runner.generate(rows,set(),16,2)
    saved=json.loads((out/'generation.json').read_text())
    assert saved['1']['steps']==16 and saved['1']['batch_ids']==[1]
    runner.ROOT=root
    preview=root/'output/krillin_japanese_lt_test/lt_4_take_2.wav';preview.parent.mkdir(parents=True)
    sf.write(preview,np.full(24000,.12345),24000,subtype='FLOAT')
    runner.generate([dict(rows[0],idx=4,reuse_preview_idx=4)],set())
    assert (out/'generated/line_004.wav').read_bytes()==preview.read_bytes(), 'Preferred take 2 was rewritten'
    # Wrapper fast options reach both output identity and child CLI.
    video=root/'episode.mkv';video.write_bytes(b'video')
    translation=root/'translation.srt';translation.write_text('1\n00:00:00,000 --> 00:00:01,000\nTikrai.\n')
    (root/'english.srt').write_bytes(translation.read_bytes())
    normal=gemini.output_directory(86,video,translation,root)
    fast=gemini.output_directory(86,video,translation,root,FAST_OPTIONS)
    assert fast!=normal
    assert gemini.output_directory(86,video,translation,root,dict(FAST_OPTIONS,steps=16))!=fast
    with patch.object(sys,'argv',['dub_gemini.py','86','--fast','--steps','16']),patch.object(gemini,'episode_files',return_value=(video,root)),patch.object(gemini,'export_package'),patch.object(gemini,'translation_file',return_value=translation),patch.object(gemini,'output_directory',return_value=fast) as directory_mock,patch.object(gemini,'reuse_audio'),patch.object(gemini.subprocess,'run') as run:
        gemini.main()
        options=directory_mock.call_args.kwargs['options']
        assert options==dict(FAST_OPTIONS,steps=16)
        command=run.call_args.args[0]
        assert command[command.index('--steps')+1]=='16'
        assert command[command.index('--reference-model')+1]=='base'
        assert command[command.index('--batch-size')+1]=='1' and '--skip-speech-check' in command
    # Source audio cache is reused across voice variants; accepted source remains unchanged.
    source=normal;source.mkdir(parents=True)
    stat=video.stat();identity=dict(video=str(video.resolve()),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)
    (source/'preparation.json').write_text(json.dumps(dict(source=identity)))
    stem=source/'separated/htdemucs/japanese/no_vocals.wav';stem.parent.mkdir(parents=True);stem.write_bytes(b'stem')
    (source/'japanese.wav').write_bytes(b'original')
    fast.mkdir(parents=True);gemini.reuse_audio(video,fast)
    assert (fast/'japanese.wav').read_bytes()==b'original'
    assert (fast/'separated/htdemucs/japanese/no_vocals.wav').read_bytes()==b'stem'
    assert (source/'japanese.wav').read_bytes()==b'original'
    # The all stage really bypasses speech_check and forwards generation settings.
    runner.OUT=out;video=root/'episode.mkv';video.touch()
    reference=out/'reference.wav';sf.write(reference,np.full(24000,.1),24000)
    row=dict(rows[0],reference=str(reference),reference_anchor_idx=1,start_sec=0,end_sec=1,source_ids=[1])
    (out/'transcript.json').write_text(json.dumps([row]))
    with patch.object(sys,'argv',['runner','--stage','all','--video',str(video),'--out-dir',str(out),'--steps','24','--batch-size','2','--skip-speech-check']),patch.object(runner.subprocess,'check_output',return_value=b'3'),patch.object(runner,'generate') as generate,patch.object(runner,'speech_check',side_effect=AssertionError('Speech checking should be skipped')),patch.object(runner,'render') as render:
        runner.main()
        assert generate.call_args.args[2:]==(24,2)
        assert render.call_args.args[1:]==(24,2,True)
print('Fast dubbing, batching, OOM fallback, cache and command checks passed')
