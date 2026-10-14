#!/usr/bin/env python3
"""Transcribe recorded Lithuanian dialogue locally for Japanese-reference dubbing."""
import argparse
import html
import json
from pathlib import Path
import subprocess

from dub_local import conversation_blocks, dialogue_rows, enable_cuda_asr, imported_transcript, run, save_json, subtitle_rows


def main():
    enable_cuda_asr()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    video = args.video.resolve();out = args.out_dir.resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if out==video.parent:
        raise ValueError('Use a separate output directory')
    out.mkdir(parents=True, exist_ok=True)
    identity = dict(video=str(video), bytes=video.stat().st_size, mtime_ns=video.stat().st_mtime_ns)
    manifest = out/'transcription.json'
    if manifest.exists():
        if json.loads(manifest.read_text())['source']!=identity:
            raise ValueError('Source changed; use a new output directory')
    elif any(out.iterdir()):
        raise ValueError('Use a fresh output directory')
    save_json(manifest, dict(source=identity, model='large-v3', language='lt', device='cuda', compute_type='int8_float16', offline=True))
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    tracks = [s for s in probe['streams'] if s['codec_type']=='audio' and s.get('tags',{}).get('language') in ('lit','lt')]
    subtitles = [s for s in probe['streams'] if s['codec_type']=='subtitle' and s.get('tags',{}).get('language')=='eng' and 'Basic Subtitles' in s.get('tags',{}).get('title','')]
    if len(tracks)!=1 or len(subtitles)!=1:
        raise ValueError('Expected one Lithuanian audio and one English Basic Subtitles track')
    audio = out/'original_lt.wav'
    if not audio.exists():
        run('ffmpeg','-v','error','-y','-i',video,'-map',f'0:{tracks[0]["index"]}','-ar','16000','-ac','1',audio)
    if not (out/'english.srt').exists():
        run('ffmpeg','-v','error','-y','-i',video,'-map',f'0:{subtitles[0]["index"]}',out/'english.srt')
    source = dialogue_rows(subtitle_rows((out/'english.srt').read_text()))
    blocks = conversation_blocks(source)
    from faster_whisper import WhisperModel
    model = None;rows = [];duration = float(probe['format']['duration'])
    for number,(first,last) in enumerate(blocks,1):
        block = source[first:last]
        start = max(0,block[0]['start_sec']-.4)
        end = min(duration,block[-1]['end_sec']+.4)
        if first:
            start = max(start,(source[first-1]['end_sec']+block[0]['start_sec'])/2)
        if last<len(source):
            end = min(end,(block[-1]['end_sec']+source[last]['start_sec'])/2)
        checkpoint = out/f'block_{number:03d}.json'
        if checkpoint.exists():
            recognized = json.loads(checkpoint.read_text())
        else:
            clip = out/'asr_clip.wav'
            run('ffmpeg','-v','error','-y','-ss',start,'-i',audio,'-t',end-start,clip)
            if model is None:
                model = WhisperModel('large-v3',device='cuda',compute_type='int8_float16',local_files_only=True)
            # ponytail: source subtitle windows exclude songs; dub-only lines outside them need listening review.
            segments,_ = model.transcribe(str(clip),language='lt',task='transcribe',beam_size=5,vad_filter=True,condition_on_previous_text=False)
            recognized = [dict(start_sec=start+s.start,end_sec=min(end,start+s.end),text=s.text.strip(),
                avg_logprob=s.avg_logprob,no_speech_prob=s.no_speech_prob,compression_ratio=s.compression_ratio) for s in segments]
            save_json(checkpoint,recognized)
        print(f'Lithuanian transcription block {number}/{len(blocks)}: {len(recognized)} phrases',flush=True)
        for segment in recognized:
            if not segment['text'] or segment['end_sec']<=segment['start_sec']:
                continue
            matched = [r for r in block if r['start_sec']<segment['end_sec'] and r['end_sec']>segment['start_sec']]
            note = 'Recorded Lithuanian ASR; verify wording, names and background-language leakage. Japanese reference speaker is automatic.'
            if segment['avg_logprob'] < -1 or segment['no_speech_prob']>.6 or segment['compression_ratio']>2.4:
                note += ' Low-confidence recognition.'
            if len(matched)!=1:
                note += ' Covers multiple Japanese cues or lacks direct alignment.'
            row = dict(idx=len(rows)+1,start_sec=segment['start_sec'],end_sec=segment['end_sec'],lt=segment['text'],
                en=' '.join(r['en'] for r in matched),source_ids=[r['idx'] for r in matched],review_note=note)
            rows.append(row)
            print(f'  #{row["idx"]}: {row["lt"]}',flush=True)
    path = out/'transcript.json'
    # Validate before committing the transcript used for speech generation.
    temporary = out/'transcript_candidate.json'
    save_json(temporary,rows)
    imported_transcript(temporary,duration)
    if not path.exists():
        temporary.replace(path)
    else:
        temporary.unlink()  # Preserve any listening corrections in an existing transcript.
    reviewed = imported_transcript(path,duration)
    page = ['<!doctype html><html lang="lt"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Original Lithuanian dialogue</title><style>body{font:17px system-ui;max-width:1100px;margin:auto;padding:24px}td,th{padding:12px;text-align:left;vertical-align:top}audio{width:100%;position:sticky;top:0}table{width:100%}</style>',
        '<h1>Original Lithuanian dialogue</h1><p>Automatic transcription of the recorded Lithuanian dub. Check names, wording and background speech by listening. Edit lt fields in <a href="transcript.json">transcript.json</a> before importing it for dubbing.</p>',
        '<audio id="original" controls preload="metadata" src="original_lt.wav"></audio>',
        '<table><thead><tr><th>Listen</th><th>Lithuanian transcript</th><th>English context / review notes</th></tr></thead><tbody>']
    for r in reviewed:
        label = f'{int(r["start_sec"]//60):02d}:{r["start_sec"]%60:05.2f}'
        page.append(f'<tr><td><button type="button" onclick="const a=document.getElementById(\'original\');a.currentTime={r["start_sec"]};a.play()">#{r["idx"]} {label}</button></td><td lang="lt">{html.escape(r["lt"])}</td><td>{html.escape(r["en"])}<p>{html.escape(r["review_note"])}</p></td></tr>')
    page.append('</tbody></table></html>')
    (out/'index.html').write_text('\n'.join(page),encoding='utf-8')
    print(f'Original Lithuanian transcript: {path}',flush=True)


if __name__=='__main__':
    main()
