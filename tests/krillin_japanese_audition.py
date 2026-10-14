#!/usr/bin/env python3
"""Generate three Lithuanian Krillin samples from Japanese references."""
import html
import json
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/krillin_japanese_lt_test'
SOURCE = ROOT / 'media/Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv'


def run(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


def checked(path):
    audio, sr = sf.read(path)
    assert len(audio) > sr / 4 and np.isfinite(audio).all(), path
    assert 0.001 < np.max(np.abs(audio)) <= 1, path
    return len(audio) / sr


def main():
    rows = json.loads((OUT / 'transcript.json').read_text())
    assert len(rows) == 3 and len({r['idx'] for r in rows}) == 3
    for r in rows:
        assert 950 <= r['start_sec'] < r['end_sec'] <= 1050
        assert r['lt'].strip() and r['reference_text'].strip()
        checked(r['reference'])
    model = OmniVoice.from_pretrained('k2-fsa/OmniVoice', device_map='cuda:0', dtype=torch.float16)
    page = ['<!doctype html><html lang="en"><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<title>Krillin: Japanese voice speaking Lithuanian</title>',
            '<style>body{font:18px system-ui;max-width:920px;margin:32px auto;padding:16px;background:#141821;color:#eee}video{width:100%;max-width:640px}audio{width:100%;max-width:640px}section{margin:32px 0}a{color:#9bd}</style>',
            '<h1>Krillin: Japanese voice speaking Lithuanian</h1>',
            '<p>Three scene-specific Japanese references, with new Lithuanian translations from English subtitles. Compare voice identity, pronunciation and expression. Both takes are available; neither was selected by listening.</p>',
            '<p>The Lithuanian video uses the separated Japanese music/effects stem. Separation can remove effects or leave dialogue residue. Dry speech is available below each video.</p>']
    for r in rows:
        i = r['idx']
        prompt = model.create_voice_clone_prompt(ref_audio=r['reference'], ref_text=r['reference_text'])
        seconds = r['end_sec'] - r['start_sec']
        original = OUT / f'original_{i}.mp4'
        run('-ss', r['start_sec'], '-i', SOURCE, '-t', seconds,
            '-map', '0:v:0', '-map', '0:2', '-c:v', 'libx264', '-preset', 'fast',
            '-crf', 18, '-c:a', 'aac', '-movflags', '+faststart', original)
        page.extend([f'<section><h2>{html.escape(r["style"])}</h2>',
                     f'<p>Episode {int(r["start_sec"]//60):02d}:{r["start_sec"]%60:05.2f}</p>',
                     f'<p>English: {html.escape(r["en"])}</p>',
                     f'<p lang="lt">Lithuanian: {html.escape(r["lt"])}</p>',
                     f'<h3>Original Japanese</h3><video controls preload="none" src="{original.name}"></video>',
                     f'<p>Isolated Japanese reference</p><audio controls preload="none" src="references/line_{i:03d}.wav"></audio>'])
        r['takes'] = []
        for take in (1, 2):
            seed = 42 + i + (take - 1) * 1000
            wav = OUT / f'lt_{i}_take_{take}.wav'
            if not wav.exists():
                torch.manual_seed(seed)
                print(f'Generating line {i}, take {take}: {r["lt"]}', flush=True)
                audio = model.generate(text=r['lt'], language='lt', voice_clone_prompt=prompt, num_step=32)[0]
                assert np.isfinite(audio).all() and len(audio) > model.sampling_rate / 4
                peak = float(np.max(np.abs(audio)))
                assert peak > 0.001
                sf.write(wav, audio * min(1, 0.95 / peak), model.sampling_rate)
            duration = checked(wav)
            # ponytail: fit each short clip to its scene; use edited translations for a full episode.
            speed = max(1, duration / seconds)
            filters = []
            remaining = speed
            while remaining > 2:
                filters.append('atempo=2')
                remaining /= 2
            filters.append(f'atempo={remaining}')
            fitted = OUT / f'fitted_{i}_{take}.wav'
            run('-i', wav, '-af', ','.join(filters) + f',apad,atrim=duration={seconds}', fitted)
            mixed = OUT / f'mixed_{i}_{take}.flac'
            run('-ss', r['start_sec'] - 950, '-i', OUT / 'separated/htdemucs/japanese_scene/no_vocals.wav',
                '-i', fitted, '-filter_complex',
                f'[0:a]atrim=duration={seconds},asetpts=PTS-STARTPTS,volume=0.65[bg];[1:a]volume=1.3[v];[bg][v]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95:level=false:latency=true[out]',
                '-map', '[out]', '-t', seconds, mixed)
            video = OUT / f'krillin_{i}_take_{take}.mp4'
            run('-i', original, '-i', mixed, '-map', '0:v:0', '-map', '1:a:0',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-t', seconds,
                '-movflags', '+faststart', video)
            checked(mixed)
            probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(video)]))
            assert abs(float(probe['format']['duration']) - seconds) < 0.15
            assert sum(s['codec_type'] == 'audio' for s in probe['streams']) == 1
            r['takes'].append(dict(take=take, seed=seed, raw_seconds=duration, fitted_speed=speed))
            page.extend([f'<h3>Lithuanian take {take}</h3><video controls preload="none" src="{video.name}"></video>',
                         f'<p>Dry generated voice, natural timing ({duration:.2f}s)</p><audio controls preload="none" src="{wav.name}"></audio>'])
        if r.get('reference_review_note'):
            page.append(f'<p>Reference review: {html.escape(r["reference_review_note"])}</p>')
        if i == 2:
            page.append('<p>Take 2 needs pronunciation review: automatic recognition identified it as Bulgarian. Start with take 1; this flag is not a listening verdict.</p>')
        page.append('</section>')
    (OUT / 'index.html').write_text('\n'.join(page), encoding='utf-8')
    (OUT / 'settings.json').write_text(json.dumps(dict(model='k2-fsa/OmniVoice', language='lt', steps=32,
        reference_transcription='Whisper large-v3 Japanese; unverified ASR',
        translation='New translations from English subtitles, authorized for this experiment',
        selection='Two takes exposed for user listening; no automatic acting judgement', lines=rows), ensure_ascii=False, indent=2))
    print(f'Validated six takes and six videos. Open {OUT / "index.html"}', flush=True)


if __name__ == '__main__':
    main()
