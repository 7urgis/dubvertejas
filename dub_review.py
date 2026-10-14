#!/usr/bin/env python3
"""Saved alternative takes and immutable rebuilt episodes for the local review UI."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import uuid

from dub_local import ROOT, checked_translations, save_json


def output_path(name):
    if not isinstance(name,str) or not re.fullmatch(r'\d{3}/[A-Za-z0-9_-]+',name):
        raise ValueError('Invalid episode output')
    path=(ROOT/'output/gemini'/name).resolve()
    if not path.is_relative_to((ROOT/'output/gemini').resolve()) or not (path/'settings.json').is_file():
        raise ValueError('Choose a completed episode render')
    return path


def row_for(out, idx):
    if type(idx) is not int:raise ValueError('Line ID must be an integer')
    rows=json.loads((out/'transcript.json').read_text())
    row=next((r for r in rows if r['idx']==idx),None)
    if row is None:raise ValueError('Unknown dialogue line')
    return row


def selection(out):
    path=out/'review/selection.json'
    return json.loads(path.read_text()) if path.exists() else {}


def take_for(out, idx, take):
    row=row_for(out,idx)
    if take in ('original','japanese'):
        return dict(id=take,idx=idx,text=row['lt'],audio=f'generated/line_{idx:03d}.wav')
    if not isinstance(take,str) or not re.fullmatch(r'[a-f0-9]{32}',take):raise ValueError('Invalid take ID')
    folder=(out/'review/takes'/take).resolve()
    if not folder.is_relative_to(out):raise ValueError('Invalid take path')
    data=json.loads((folder/'take.json').read_text())
    if data['idx']!=idx:raise ValueError('Take belongs to a different line')
    audio=(folder/'generated'/f'line_{idx:03d}.wav').resolve()
    if not audio.is_relative_to(out) or not audio.is_file():raise ValueError('Take audio is missing')
    return dict(data,audio=audio.relative_to(out).as_posix())


def review_data(out):
    selected=selection(out);rows=json.loads((out/'transcript.json').read_text())
    by_id={r['idx']:dict(idx=r['idx'],text=r['lt'],start_sec=r['start_sec'],end_sec=r['end_sec'],
        selected=selected.get(str(r['idx']),'japanese' if r.get('keep_japanese') else 'original'),takes=[]) for r in rows}
    for file in sorted((out/'review/takes').glob('*/take.json'),key=lambda p:p.stat().st_mtime_ns):
        data=json.loads(file.read_text())
        if data['idx'] in by_id:by_id[data['idx']]['takes'].append(take_for(out,data['idx'],file.parent.name))
    history=out/'review/renders.json'
    return dict(rows=list(by_id.values()),dirty=bool(selected),renders=json.loads(history.read_text()) if history.exists() else [])


def select_take(out, idx, take):
    take_for(out,idx,take)
    choices=selection(out)
    baseline='japanese' if row_for(out,idx).get('keep_japanese') else 'original'
    if take==baseline:choices.pop(str(idx),None)
    else:choices[str(idx)]=take
    (out/'review').mkdir(exist_ok=True)
    save_json(out/'review/selection.json',choices)


def regeneration_request(out, idx, text):
    row=row_for(out,idx)
    text=checked_translations({'translations':{str(idx):text}},[row])[idx]
    token=uuid.uuid4().hex;folder=out/'review/takes'/token;folder.mkdir(parents=True)
    request=folder/'request.json'
    save_json(request,dict(action='regenerate',output=out.relative_to(ROOT/'output/gemini').as_posix(),idx=idx,
        text=text,take=token,seed=secrets.randbelow(2**31)))
    return request


def rebuild_request(out):
    choices=selection(out)
    if not choices:raise ValueError('Choose a new take before rebuilding the video')
    for idx,take in choices.items():take_for(out,int(idx),take)
    destination=out.parent/('edit-'+uuid.uuid4().hex);destination.mkdir()
    request=destination/'request.json'
    save_json(request,dict(action='rebuild',output=out.relative_to(ROOT/'output/gemini').as_posix(),selected=choices,
        destination=destination.relative_to(ROOT/'output/gemini').as_posix()))
    return request,destination


def run_request(request):
    data=json.loads(request.read_text());out=output_path(data['output'])
    settings=json.loads((out/'settings.json').read_text())
    spec=importlib.util.spec_from_file_location('episode_runner',ROOT/'tests/japanese_cast_episode.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    if data['action']=='regenerate':
        # ponytail: one model load per edit; use a resident worker if repeated edits need lower startup latency.
        row=dict(row_for(out,data['idx']))
        row['lt']=checked_translations({'translations':{str(row['idx']):data['text']}},[row])[row['idx']]
        if type(data['seed']) is not int or not 0<=data['seed']<2**31:raise ValueError('Invalid generation seed')
        if not re.fullmatch(r'[a-f0-9]{32}',data['take']):raise ValueError('Invalid take ID')
        folder=out/'review/takes'/data['take']
        if request.resolve()!=(folder/'request.json').resolve():raise ValueError('Invalid request path')
        reference=Path(row['reference']).resolve()
        if not reference.is_relative_to((ROOT/'output').resolve()):raise ValueError('Invalid reference path')
        refs=folder/'references';refs.mkdir(exist_ok=True)
        copied=refs/reference.name;shutil.copyfile(reference,copied)
        row.update(reference=str(copied),generation_seed=data['seed'])
        row.pop('reuse_preview_idx',None)
        runner.OUT=folder
        runner.generate([row],set(),steps=settings.get('steps',32))
        save_json(folder/'take.json',dict(id=data['take'],idx=row['idx'],text=row['lt'],seed=data['seed'],steps=settings.get('steps',32)))
        print(f'New take ready for line {row["idx"]}',flush=True)
        return
    if data['action']!='rebuild':raise ValueError('Unknown review action')
    destination=(ROOT/'output/gemini'/data['destination']).resolve()
    if destination.parent!=out.parent or not re.fullmatch(r'edit-[a-f0-9]{32}',destination.name) or request.resolve()!=destination/'request.json':
        raise ValueError('Invalid rebuild destination')
    if (destination/'settings.json').exists():raise ValueError('This rebuild is already completed')
    video=Path(settings['video']).resolve()
    if not video.is_relative_to((ROOT/'media').resolve()) or not video.is_file():raise ValueError('Original video is missing')
    rows=json.loads((out/'transcript.json').read_text())
    generated=destination/'generated';generated.mkdir(exist_ok=True)
    refs=destination/'references';refs.mkdir(exist_ok=True)
    metadata=json.loads((out/'generation.json').read_text());steps=settings.get('steps',32);batch=settings.get('batch_size',1)
    for row in rows:
        idx=row['idx'];take=take_for(out,idx,data['selected'].get(str(idx),'japanese' if row.get('keep_japanese') else 'original'))
        row['keep_japanese']=take['id']=='japanese'
        audio=(out/take['audio']).resolve()
        if not audio.is_relative_to(out):raise ValueError('Invalid audio path')
        runner.validated(audio)
        row['lt']=take['text']
        reference=Path(row['reference']).resolve()
        if not reference.is_relative_to((ROOT/'output').resolve()):raise ValueError('Invalid reference path')
        copied=refs/f'line_{idx:03d}.wav';shutil.copyfile(reference,copied);row['reference']=str(copied)
        shutil.copyfile(audio,generated/f'line_{idx:03d}.wav')
        if take['id'] not in ('original','japanese'):
            row['generation_seed']=take['seed'];row.pop('reuse_preview_idx',None)
            metadata[str(idx)]=json.loads((audio.parent.parent/'generation.json').read_text())[str(idx)]
        metadata[str(idx)].update(fingerprint=runner.fingerprint(row,steps,batch),selected_take=take['id'])
    save_json(destination/'transcript.json',rows);save_json(destination/'generation.json',metadata)
    for name in ('preparation.json','skipped_references.json','glossary.md','episode_context.md','english.srt','imported_translation.srt'):
        if (out/name).is_file():shutil.copyfile(out/name,destination/name)
    subprocess.run(['cp','-r','--update=none','--reflink=auto',str(out/'japanese.wav'),str(out/'separated'),str(destination)],check=True)
    save_json(destination/'review_source.json',dict(source=data['output'],selected=data['selected']))
    runner.OUT=destination;runner.SOURCE=video
    runner.DURATION=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video)]))
    # Rebuilding only mixes/remuxes selected clips, without another generation or ASR pass.
    runner.render(rows,steps=steps,batch_size=batch,skip_speech_check=True)
    history=out/'review/renders.json';renders=json.loads(history.read_text()) if history.exists() else []
    renders.append(data['destination']);save_json(history,renders)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True)
    run_request(parser.parse_args().request)
