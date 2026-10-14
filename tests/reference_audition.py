#!/usr/bin/env python3
"""Compare the old actor reference with original and separated episode 068 speech."""
import html
import json
from pathlib import Path
import shutil

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

from voice_audition import ROOT, LINES


def main():
    info = json.loads((ROOT / "data/samples/reference_ep068_9s.json").read_text())
    variants = [
        ("old", "Current reference, 4.5 seconds", ROOT / "data/samples/reference_90s_actor.flac", "Selas netrukus taps visagalis."),
        ("raw", "Episode 068, 9.2 seconds, original audio", ROOT / info["raw"], info["transcript"]),
        ("vocals", "Episode 068, 9.2 seconds, music reduced", ROOT / info["vocals"], info["transcript"]),
    ]
    lines = LINES + [("Pronunciation", "Kova tarp Pikolo ir roboto numeris septyniolika jau prasidėjo.")]
    out = ROOT / "output/reference_audition"
    out.mkdir(parents=True, exist_ok=True)
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)
    for name, label, reference, transcript in variants:
        folder = out / name
        folder.mkdir(exist_ok=True)
        shutil.copyfile(reference, folder / "reference.flac")
        prompt = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=transcript)
        for i, (kind, text) in enumerate(lines, 1):
            # Identical per-line seeds make reference choice the controlled variable.
            torch.manual_seed(42 + i)
            print(f"{label}: {kind}", flush=True)
            audio = model.generate(text=text, language="lt", voice_clone_prompt=prompt, num_step=32)[0]
            if (len(audio) < model.sampling_rate / 2 or not np.isfinite(audio).all()
                    or np.max(np.abs(audio)) < 0.001):
                raise ValueError(f"Invalid output: {name}, line {i}")
            sf.write(folder / f"line_{i:03d}.wav", audio, model.sampling_rate)
    page = ['<!doctype html><html lang="en"><meta charset="utf-8">',
            '<title>Actor reference comparison</title>',
            '<style>body{font:18px system-ui;max-width:1100px;margin:40px auto;padding:16px}td,th{padding:8px;text-align:left}audio{width:300px}</style>',
            '<h1>Actor reference comparison</h1><p>OmniVoice only. Same text, per-line random seed and 32 generation steps. Listen for Lithuanian stress, natural pauses, consistent voice and background artifacts.</p>',
            '<h2>Reference recordings</h2><p>New passage: episode 068, 03:55.1–04:04.3. Music reduction can introduce artifacts and does not guarantee removal of other speaking voices.</p>']
    for name, label, _, transcript in variants:
        page.append(f'<h3>{html.escape(label)}</h3><audio controls src="{name}/reference.flac"></audio><p lang="lt">{html.escape(transcript)}</p>')
    page.append('<p>The new reference transcript was transcribed automatically and spelling corrected. Please verify it against the recording before adopting it for a full episode.</p>')
    for i, (kind, text) in enumerate(lines, 1):
        page.append(f'<h2>{html.escape(kind)}</h2><p lang="lt">{html.escape(text)}</p><table>')
        for name, label, _, _ in variants:
            clip = out / name / f"line_{i:03d}.wav"
            audio, sr = sf.read(clip)
            assert len(audio) > sr / 2 and np.isfinite(audio).all(), clip
            page.append(f'<tr><th>{html.escape(label)}</th><td><audio controls preload="none" src="{clip.relative_to(out).as_posix()}"></audio></td></tr>')
        page.append('</table>')
    (out / "index.html").write_text('\n'.join(page), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps({
        "model": "k2-fsa/OmniVoice", "num_step": 32, "per_line_seed": "42 + line number",
        "new_reference": info, "lines": lines,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Open {out / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
