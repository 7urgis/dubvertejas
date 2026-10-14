#!/usr/bin/env python3
"""Render a prepared episode using Lithuanian lines and Japanese voice references.
Run with tools/Applio/.venv/bin/python tests/japanese_cast_episode.py --stage generate|check|render.
Use dub_local.py for automatic offline preparation; defaults preserve the episode 149 workflow.
"""
import argparse
import os
import difflib
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'

import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/omnivoice_149_japanese_cast'
SOURCE = ROOT / 'media/Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv'
DURATION = 1481.605


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


def validated(path):
    audio, sr = sf.read(path, dtype='float32')
    if not len(audio) or not np.isfinite(audio).all() or not 0.001 < float(np.max(np.abs(audio))) <= 1:
        raise ValueError(f'Invalid audio: {path}')
    return audio, sr


def fingerprint(row, steps=32, batch_size=1):
    data={k:row.get(k) for k in ('lt','reference','reference_text','speaker','reuse_preview_idx')}
    if 'generation_seed' in row:data['generation_seed']=row['generation_seed']
    if (steps,batch_size)!=(32,1):data.update(steps=steps,batch_size=batch_size)
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def generate(rows, repairs, steps=32, batch_size=1):
    rows=[r for r in rows if not r.get('keep_japanese')]
    if not rows:return
    generated=OUT/'generated';generated.mkdir(exist_ok=True)
    settings_path=OUT/'generation.json'
    saved=json.loads(settings_path.read_text()) if settings_path.exists() else {}
    pending=[]
    for r in rows:
        key=str(r['idx']);path=generated/f'line_{r["idx"]:03d}.wav'
        if path.exists() and saved.get(key,{}).get('fingerprint')==fingerprint(r,steps,batch_size) and r['idx'] not in repairs:
            validated(path)
        else:pending.append(r)
    if not pending:
        print('All generated voices cached; no model loading needed',flush=True)
        return
    import torch
    from omnivoice import OmniVoice
    model=OmniVoice.from_pretrained('k2-fsa/OmniVoice',device_map='cuda:0',dtype=torch.float16)
    prompts={}

    def store(r,audio,metadata):
        peak=float(np.max(np.abs(audio)))
        if len(audio)<model.sampling_rate/4 or not np.isfinite(audio).all() or peak<=0.001:
            raise ValueError(f'Invalid generation #{r["idx"]}')
        path=generated/f'line_{r["idx"]:03d}.wav'
        if r['idx'] in repairs and path.exists():shutil.copyfile(path,generated/f'previous_{r["idx"]:03d}.wav')
        sf.write(path,audio*min(1,0.95/peak),model.sampling_rate)
        saved[str(r['idx'])]=dict(metadata,fingerprint=fingerprint(r,steps,batch_size),seconds=len(audio)/model.sampling_rate,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),repair=r['idx'] in repairs)
        write(settings_path,saved)

    def run_batch(batch):
        for r in batch:
            reference=r['reference']
            if reference not in prompts:
                prompts[reference]=model.create_voice_clone_prompt(ref_audio=reference,ref_text=r['reference_text'])
        seed=batch[0].get('generation_seed',1042+batch[0]['idx']+(1000 if batch[0]['idx'] in repairs else 0))
        torch.manual_seed(seed)
        print(f'Generating {len(batch)} line(s), {steps} steps: '+', '.join(str(r['idx']) for r in batch),flush=True)
        started=time.perf_counter()
        try:
            audio=model.generate(text=[r['lt'] for r in batch],language='lt',
                voice_clone_prompt=[prompts[r['reference']] for r in batch],num_step=steps)
        except torch.cuda.OutOfMemoryError:
            if len(batch)==1:raise
            audio=None
        if audio is None:
            # Retry after the exception scope releases tensors retained by its traceback.
            torch.cuda.empty_cache()
            print('Batch exceeds GPU memory; retrying one line at a time',flush=True)
            for r in batch:run_batch([r])
            return
        if len(audio)!=len(batch):raise ValueError('Generation returned the wrong number of lines')
        elapsed=time.perf_counter()-started
        for r,wave in zip(batch,audio):
            store(r,wave,dict(seed=seed,steps=steps,batch_ids=[x['idx'] for x in batch],batch_seconds=elapsed))
        print(f'Batch completed in {elapsed:.2f}s',flush=True)

    # ponytail: batch size capped at 2 for the 8 GB GPU; larger batches need a separate memory benchmark.
    fresh=[]
    for r in pending:
        if r.get('reuse_preview_idx') and r['idx'] not in repairs and (steps,batch_size)==(32,1):
            original=ROOT/'output/krillin_japanese_lt_test'/f'lt_{r["reuse_preview_idx"]}_take_2.wav'
            wave,sr=validated(original)
            assert sr==model.sampling_rate
            path=generated/f'line_{r["idx"]:03d}.wav'
            shutil.copyfile(original,path)
            saved[str(r['idx'])]=dict(fingerprint=fingerprint(r),reused=str(original),take=2,steps=32,
                seconds=len(wave)/sr,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            write(settings_path,saved)
        else:fresh.append(r)
    for start in range(0,len(fresh),batch_size):run_batch(fresh[start:start+batch_size])


def normalized(text):
    return re.sub(r'[^\w]','',text.lower())


def speech_check(rows, device='cpu'):
    rows=[r for r in rows if not r.get('keep_japanese')]
    if not rows:return
    if device=='cuda':
        import torch
        torch.cuda.empty_cache()
    from faster_whisper import WhisperModel
    model=WhisperModel('large-v3',device=device,compute_type='int8_float16' if device=='cuda' else 'int8',cpu_threads=8,local_files_only=True)
    destination=OUT/'speech_check.json'
    cache=json.loads(destination.read_text()) if destination.exists() else {}
    for n,r in enumerate(rows,1):
        path=OUT/'generated'/f'line_{r["idx"]:03d}.wav';digest=hashlib.sha256(path.read_bytes()).hexdigest();key=str(r['idx'])
        if cache.get(key,{}).get('sha256')==digest:continue
        segments,info=model.transcribe(str(path),beam_size=5,vad_filter=False)
        auto=' '.join(s.text.strip() for s in segments)
        text=auto
        if info.language!='lt':
            segments,_=model.transcribe(str(path),language='lt',beam_size=5,vad_filter=False)
            text=' '.join(s.text.strip() for s in segments)
        score=difflib.SequenceMatcher(None,normalized(r['lt']),normalized(text)).ratio()
        cache[key]=dict(sha256=digest,language=info.language,language_probability=info.language_probability,
                       auto_text=auto,lt_text=text,expected=r['lt'],similarity=score,review=score<0.65 or info.language!='lt')
        write(destination,cache)
        print(f'{n}/{len(rows)} #{key} {info.language} similarity={score:.2f}: {text}',flush=True)


def timestamp(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}'


def render(rows, steps=32, batch_size=1, skip_speech_check=False):
    review_rows=rows
    japanese_rows=[r for r in rows if r.get('keep_japanese')]
    rows=[r for r in rows if not r.get('keep_japanese')]
    sr=24000;canvas=np.zeros(round(DURATION*sr),dtype=np.float32);placements=[]
    skipped_path=OUT/'skipped_references.json'
    skipped=json.loads(skipped_path.read_text()) if skipped_path.exists() else []
    skipped+=japanese_rows
    fitted=OUT/'fitted';fitted.mkdir(exist_ok=True)
    for n,r in enumerate(rows):
        path=OUT/'generated'/f'line_{r["idx"]:03d}.wav';audio,actual=validated(path)
        assert actual==sr
        limit=min(r['end_sec']+.12,rows[n+1]['start_sec'] if n+1<len(rows) else DURATION)
        available=limit-r['start_sec'];assert available>0
        speed=max(1,len(audio)/sr/available)
        if speed>1:
            filters=[];remaining=speed
            while remaining>2:filters.append('atempo=2');remaining/=2
            filters.append(f'atempo={remaining}')
            adjusted=fitted/path.name
            ffmpeg('-i',path,'-af',','.join(filters),adjusted)
            audio,actual=validated(adjusted);audio=audio[:round(available*sr)]
        start=round(r['start_sec']*sr);end=start+len(audio);assert end<=len(canvas)
        canvas[start:end]+=audio
        placements.append(dict(idx=r['idx'],start_sec=r['start_sec'],end_sec=end/sr,speed=speed))
    for r in skipped:
        canvas[max(0,round(r['start_sec']*sr)):round(r['end_sec']*sr)]=0
    peak=float(np.max(np.abs(canvas)))
    if rows:
        assert peak>0
        canvas*=min(1,0.95/peak)
    sf.write(OUT/'ai_voice.flac',canvas,sr)
    write(OUT/'placements.json',placements)
    # ponytail: speech windows replace Japanese dialogue; exact vocal/effect separation needs dedicated stems.
    original,bsr=validated(OUT/'japanese.wav')
    background,ssr=validated(OUT/'separated/htdemucs/japanese/no_vocals.wav')
    assert bsr==ssr==44100 and original.shape==background.shape
    mask=np.zeros(len(original),dtype=np.float32)
    for r,p in zip(rows,placements):
        start=max(0,round((r['start_sec']-.1)*bsr));end=min(len(mask),round((max(r['end_sec'],p['end_sec'])+.12)*bsr))
        mask[start:end]=1
    # Smooth transitions while fully suppressing source vocals in the dialogue window.
    mask=uniform_filter1d(mask,size=round(.06*bsr),mode='constant')
    for r in skipped:
        mask[max(0,round(r['start_sec']*bsr)):round(r['end_sec']*bsr)]=0
    bg=original*(1-mask[:,None])+background*mask[:,None]
    sf.write(OUT/'background.flac',bg,bsr)
    ffmpeg('-i',OUT/'background.flac','-i',OUT/'ai_voice.flac','-filter_complex',
           f'[0:a]volume=0.65,apad,atrim=duration={DURATION}[bg];[1:a]volume=1.3[v];[bg][v]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95:level=false:latency=true[out]',
           '-map','[out]','-t',DURATION,OUT/'mixed.flac')
    video=OUT/(SOURCE.name.split('.480p')[0]+'.LT-Japanese-Voices.mp4')
    ffmpeg('-i',SOURCE,'-i',OUT/'mixed.flac','-map','0:v:0','-map','1:a:0','-t',DURATION,
           '-c:v','copy','-c:a','aac','-b:a','256k','-metadata:s:a:0','language=lit','-movflags','+faststart',video)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)]))
    assert abs(float(probe['format']['duration'])-DURATION)<.1
    assert sum(s['codec_type']=='audio' for s in probe['streams'])==1
    ffmpeg('-i',video,'-map','0:a:0','-f','null','-')
    for name in (('ai_voice.flac','background.flac','mixed.flac') if rows else ('background.flac','mixed.flac')):validated(OUT/name)
    checks=json.loads((OUT/'speech_check.json').read_text()) if not skip_speech_check and (OUT/'speech_check.json').exists() else {}
    captions=['WEBVTT\n'];page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Japanese voices speaking Lithuanian</title>',
        '<style>body{font:17px system-ui;max-width:1100px;margin:32px auto;padding:16px;background:#141821;color:#eee}video{width:100%}audio{max-width:100%}a{color:#9bd}td,th{padding:10px;text-align:left;vertical-align:top}table{width:100%}button{font:inherit}</style>',
        f'<h1>{html.escape(SOURCE.name.split(".480p")[0])}: Japanese voices speaking Lithuanian</h1>',
        '<p>Lithuanian speech generated from Japanese scene references. Songs and nonverbal sounds remain Japanese. Automatically prepared translations and speaker assignments need review; short or multi-speaker references can reduce voice consistency.</p>',
        f'<video id="video" controls preload="metadata" src="{video.name}"><track kind="subtitles" src="transcript.vtt" srclang="lt" label="Lietuvių" default></video>',
        '<p><a href="'+video.name+'">Download video</a></p><h2>Dry AI voices</h2><audio controls preload="none" src="ai_voice.flac"></audio>',
        '<h2>Original Japanese soundtrack</h2><audio controls preload="none" src="japanese.wav"></audio>',
        '<h2>Dialogue review</h2><table><thead><tr><th>Time / character</th><th>Text</th><th>Dry voice / reference</th></tr></thead><tbody>']
    if skip_speech_check:page.insert(6,'<p>Generated speech checking was skipped for this render. Listen for missing or incorrect words.</p>')
    for r in review_rows:
        i=r['idx']
        if not r.get('keep_japanese'):captions.append(f'{i}\n{timestamp(r["start_sec"])} --> {timestamp(r["end_sec"])}\n{r["lt"]}\n')
        flag=checks.get(str(i),{})
        note=r.get('review_note','')
        if r.get('keep_japanese'):note+=' Original Japanese selected for this line.'
        if flag.get('review'):note+=' Automatic recognition flagged this take; this is not a listening verdict.'
        reference=Path(r['reference']).relative_to(OUT).as_posix()
        page.append(f'<tr><td><button type="button" data-time="{r["start_sec"]}">{timestamp(r["start_sec"])}</button><br>{html.escape(r["speaker"])}</td><td lang="lt">{html.escape(r["lt"])}<p lang="en">{html.escape(r["en"])}</p><small lang="en">{html.escape(note)}</small></td><td><audio controls preload="none" src="generated/line_{i:03d}.wav" aria-label="Lithuanian line {i}"></audio><br><audio controls preload="none" src="{reference}" aria-label="Japanese reference for line {i}"></audio></td></tr>')
    page.append('</tbody></table><script>document.querySelectorAll("button[data-time]").forEach(b=>b.addEventListener("click",()=>{const v=document.getElementById("video");v.currentTime=Number(b.dataset.time);v.play();v.scrollIntoView({behavior:"smooth",block:"center"});}));</script>')
    (OUT/'index.html').write_text('\n'.join(page),encoding='utf-8');(OUT/'transcript.vtt').write_text('\n'.join(captions),encoding='utf-8')
    write(OUT/'verification.json',dict(duration=DURATION,lines=len(rows),speakers=sorted({r['speaker'] for r in rows}),
        finite_non_silent_audio=True,video_duration=float(probe['format']['duration']),audio_streams=1,
        decode_passed=True,speech_check_skipped=skip_speech_check,max_tempo=max((p['speed'] for p in placements),default=1),recognition_review_ids=[int(i) for i,r in checks.items() if r['review']]))
    write(OUT/'settings.json',dict(video=str(SOURCE),model='k2-fsa/OmniVoice',steps=steps,batch_size=batch_size,speech_check_skipped=skip_speech_check,language='lt',seed_pattern='1042 + first subtitle ID; preferred take 2',
        translation='Lithuanian input transcript; see preparation.json for automatic translation provenance',reference_source='Japanese vocals separated with htdemucs',
        reference_transcription='Local Whisper, Japanese; see preparation.json for the model; ASR not fully listening-verified',
        mix='original Japanese outside dialogue; no-vocals Japanese inside dialogue; bg 0.65, voice 1.3, limiter 0.95',
        generation='Natural timing; tempo fitting only when speech exceeds scene space',preferred_preview_take=2))
    print(f'Complete: {OUT/"index.html"}',flush=True)


def main():
    global SOURCE, OUT, DURATION
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=('generate','check','render','all'),required=True);parser.add_argument('--repair',type=int,nargs='*',default=[]);parser.add_argument('--video',type=Path,default=SOURCE);parser.add_argument('--out-dir',type=Path,default=OUT);parser.add_argument('--asr-device',choices=('cpu','cuda'),default='cpu')
    parser.add_argument('--steps',type=int,choices=(16,24,32),default=32)
    parser.add_argument('--batch-size',type=int,choices=(1,2),default=1)
    parser.add_argument('--skip-speech-check',action='store_true')
    args=parser.parse_args()
    if args.asr_device=='cuda':
        sys.path.insert(0,str(ROOT))
        from dub_local import enable_cuda_asr
        enable_cuda_asr()
    SOURCE=args.video.resolve();OUT=args.out_dir.resolve()
    if not SOURCE.is_file():raise FileNotFoundError(SOURCE)
    if (OUT/'settings.json').exists():
        previous=json.loads((OUT/'settings.json').read_text())
        if previous.get('video') and previous['video']!=str(SOURCE):raise ValueError('Use a fresh output directory for another video')
        if (previous.get('steps',32),previous.get('batch_size',1),previous.get('speech_check_skipped',False))!=(args.steps,args.batch_size,args.skip_speech_check):raise ValueError('Voice settings changed; use a fresh output directory to preserve the finished render')
    if SOURCE.name!='Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv' and OUT==(ROOT/'output/omnivoice_149_japanese_cast').resolve():raise ValueError('Use a separate --out-dir to preserve episode 149')
    DURATION=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(SOURCE)]))
    rows=json.loads((OUT/'transcript.json').read_text());seen=set()
    for n,r in enumerate(rows):
        assert isinstance(r['idx'],int) and r['idx'] not in seen;seen.add(r['idx'])
        assert 0<=r['start_sec']<r['end_sec']<=DURATION and r['lt'].strip() and r['reference_text'].strip()
        assert n==0 or rows[n-1]['end_sec']<=r['start_sec']
        validated(r['reference'])
    source_ids=[i for r in rows for i in r['source_ids']]
    preparation=json.loads((OUT/'preparation.json').read_text()) if (OUT/'preparation.json').exists() else {}
    if preparation.get('translation_profile',{}).get('backend')!='recorded_transcript':
        assert len(source_ids)==len(set(source_ids))
    for r in rows:
        if isinstance(r['reference_anchor_idx'],int):
            anchor=next(x for x in rows if x['idx']==r['reference_anchor_idx'])
            assert anchor['speaker']==r['speaker']
    assert set(args.repair)<=seen
    if args.stage in ('generate','all'):generate(rows,set(args.repair),args.steps,args.batch_size)
    if args.stage=='check' or (args.stage=='all' and not args.skip_speech_check):speech_check(rows,args.asr_device)
    if args.stage in ('render','all'):render(rows,args.steps,args.batch_size,args.skip_speech_check)


if __name__=='__main__':main()
