"""Run: tools/Applio/.venv/bin/python tests/test_reference_fallback.py"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dub_local as dub
from dub_gemini import output_directory

clean=SimpleNamespace(text='こんにちは',compression_ratio=1,no_speech_prob=.1,avg_logprob=-.3)
assert dub.reference_text([clean])==clean.text
assert dub.reference_text([])==''
for field,value in [('compression_ratio',3),('no_speech_prob',.9),('avg_logprob',-2)]:
    assert not dub.reference_text([SimpleNamespace(**(vars(clean)|{field:value}))])

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);out=root/'prepared';out.mkdir()
    video=root/'episode.mkv';video.write_bytes(b'video')
    translation=root/'translation.srt'
    translation.write_text('1\n00:00:00,100 --> 00:00:00,500\nTikrai.\n\n2\n00:00:00,500 --> 00:00:01,000\nSonai!\n\n3\n00:00:01,000 --> 00:00:01,500\nGerai.\n')
    (out/'english.srt').write_bytes(translation.read_bytes())
    rows=dub.dialogue_rows(dub.subtitle_rows(translation.read_text()))
    dub.save_json(out/'transcript.json',rows)
    identity=dict(video=str(video),bytes=video.stat().st_size,mtime_ns=video.stat().st_mtime_ns)
    profile=dict(backend='import',model=None,translation_sha256=hashlib.sha256(translation.read_bytes()).hexdigest(),version=1)
    dub.save_json(out/'preparation.json',dict(source=identity,translation_profile=profile))
    (out/'japanese.wav').touch()
    stem=out/'separated/htdemucs/japanese/vocals.wav';stem.parent.mkdir(parents=True);stem.touch()
    calls=[]
    class Whisper:
        def __init__(self,*args,**kwargs):pass
        def transcribe(self,path,**kwargs):
            calls.append(Path(path).name)
            segments=[] if '002' in path else [clean]
            return iter(segments),None
    def crop(*args):Path(args[-1]).touch()
    probe=dict(format=dict(duration='3'),streams=[dict(codec_type='audio',index=0,tags=dict(language='jpn')),dict(codec_type='subtitle',index=1,tags=dict(language='eng',title='Basic Subtitles'))])
    with patch.dict(sys.modules,{'faster_whisper':SimpleNamespace(WhisperModel=Whisper)}),patch.object(dub.subprocess,'check_output',return_value=json.dumps(probe).encode()),patch.object(dub,'run',side_effect=crop):
        dub.prepare(video,out,translation_file=translation)
        first_calls=len(calls)
        dub.prepare(video,out,translation_file=translation)
        assert len(calls)==first_calls, 'Resume retried skipped or cached references'
    selected=json.loads((out/'transcript.json').read_text())
    skipped=json.loads((out/'skipped_references.json').read_text())
    assert [r['idx'] for r in selected]==[1,3]
    assert skipped[0]['idx']==2 and skipped[0]['lt']=='Sonai!'
    assert [r['lt'] for r in selected]==['Tikrai.','Gerai.']
    # Recover an interruption between saving skipped decisions and saving the transcript.
    selected.insert(1,skipped[0]);dub.save_json(out/'transcript.json',selected)
    with patch.dict(sys.modules,{'faster_whisper':SimpleNamespace(WhisperModel=Whisper)}),patch.object(dub.subprocess,'check_output',return_value=json.dumps(probe).encode()),patch.object(dub,'run',side_effect=crop):
        dub.prepare(video,out,translation_file=translation)
    assert [r['idx'] for r in json.loads((out/'transcript.json').read_text())]==[1,3]
    # Interrupted legacy outputs resume, while completed versions stay separate.
    content=json.dumps(identity,sort_keys=True).encode()+translation.read_bytes()
    legacy=root/'output/gemini/086'/hashlib.sha256(content).hexdigest()[:12]
    legacy.mkdir(parents=True);(legacy/'preparation.json').write_text('{}')
    assert output_directory(86,video,translation,root)==legacy
    (legacy/'settings.json').write_text('{}')
    assert output_directory(86,video,translation,root)!=legacy

# Exercise the real mixer, including an entirely Japanese episode and adjacent fallback.
import numpy as np
import soundfile as sf
spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('japanese_cast_episode.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
with tempfile.TemporaryDirectory() as directory:
    out=Path(directory);runner.OUT=out;runner.DURATION=3
    runner.SOURCE=out/'test.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=32x32:rate=25:duration=3','-c:v','mpeg4',str(runner.SOURCE)],check=True)
    sr=44100;t=np.arange(sr*3)/sr
    original=np.column_stack([.15*np.sin(t*2*np.pi*300)]*2).astype('float32')
    sf.write(out/'japanese.wav',original,sr,subtype='FLOAT')
    stem=out/'separated/htdemucs/japanese/no_vocals.wav';stem.parent.mkdir(parents=True)
    sf.write(stem,original*.2,sr,subtype='FLOAT')
    runner.generate([],set());runner.speech_check([])
    runner.render([])
    background,_=sf.read(out/'background.flac')
    assert np.max(np.abs(background-original))<.0001
    (out/'generated').mkdir();sf.write(out/'generated/line_001.wav',np.full(24000,.2,dtype='float32'),24000)
    reference=out/'reference.wav';sf.write(reference,np.full(24000,.1,dtype='float32'),24000)
    row=dict(idx=1,start_sec=0,end_sec=1,lt='Tikrai.',en='Yes.',speaker='Test',reference=str(reference))
    (out/'skipped_references.json').write_text(json.dumps([dict(idx=2,start_sec=1,end_sec=2)]))
    runner.render([row])
    background,_=sf.read(out/'background.flac');ai,aisr=sf.read(out/'ai_voice.flac')
    assert np.max(np.abs(background[sr:2*sr]-original[sr:2*sr]))<.0001
    assert not np.any(ai[aisr:2*aisr]), 'AI spilled into fallback window'
    runner.render([row],steps=24,skip_speech_check=True)
    assert json.loads((out/'verification.json').read_text())['speech_check_skipped']
    assert json.loads((out/'settings.json').read_text())['steps']==24
    assert 'speech checking was skipped' in (out/'index.html').read_text()
print('Reference fallback and Japanese mix checks passed')
