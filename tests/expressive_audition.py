#!/usr/bin/env python3
"""Compare reference-conditioned OmniVoice with neutral TTS and RVC."""
import html
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

from voice_audition import LINES, ROOT
from pipeline import find_rvc_model_files


def main():
    out = ROOT / "output/voice_audition"
    raw = out / "omnivoice"
    converted = out / "omnivoice_rvc"
    raw.mkdir(parents=True, exist_ok=True)
    converted.mkdir(exist_ok=True)
    transcript = (out / "reference_transcript.txt").read_text().strip()
    if not transcript:
        raise ValueError("Reference transcript is empty")
    torch.manual_seed(42)
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16
    )
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(ROOT / "data/samples/reference_90s_actor.flac"),
        ref_text=transcript,
    )
    for i, (kind, text) in enumerate(LINES, 1):
        print(f"Generating {kind}: {text}", flush=True)
        audio = model.generate(text=text, language="lt", voice_clone_prompt=prompt, num_step=32)[0]
        if not np.isfinite(audio).all() or len(audio) < model.sampling_rate / 2:
            raise ValueError(f"Invalid generated audio for line {i}")
        sf.write(raw / f"line_{i:03d}.wav", audio, model.sampling_rate)
    del prompt, model
    torch.cuda.empty_cache()
    pth, index = find_rvc_model_files(str(ROOT / "models/dbz_actor"))
    applio = ROOT / "tools/Applio"
    subprocess.run([
        str(applio / ".venv/bin/python"), "core.py", "batch-infer",
        "--input-folder", str(raw), "--output-folder", str(converted),
        "--pth-path", pth, "--index-path", index,
        "--index-rate", "0.35", "--protect", "0.33",
        "--f0-method", "rmvpe", "--pitch", "0", "--export-format", "WAV",
    ], cwd=applio, check=True)
    page = ['<!doctype html><html lang="en"><meta charset="utf-8">',
            '<title>Expressive speech test</title>',
            '<style>body{font:18px system-ui;max-width:1000px;margin:40px auto;padding:16px}td,th{padding:8px;text-align:left}audio{width:280px}</style>',
            '<h1>Expressive speech test</h1><p>OmniVoice uses the existing Lithuanian actor reference. Emotion labels describe the desired delivery, not a guaranteed model capability. Compare expression, pronunciation, word stress and voice quality.</p>',
            '<p><a href="index.html">Previous comparison</a></p>',
            '<h2>Human benchmark</h2><audio controls src="human_input/reference.wav"></audio>']
    groups = [("base", "Neutral Edge TTS"), ("low_index", "Neutral Edge TTS + RVC"),
              ("omnivoice", "OmniVoice with actor reference"),
              ("omnivoice_rvc", "OmniVoice + RVC, index 0.35, cleaning off")]
    for i, (kind, text) in enumerate(LINES, 1):
        page.append(f'<h2>{html.escape(kind)}</h2><p lang="lt">{html.escape(text)}</p><table>')
        for folder, label in groups:
            files = sorted((out / folder).glob(f"line_{i:03d}*.wav"))
            assert len(files) == 1, f"Missing or ambiguous output: {folder}, {i}"
            audio, sr = sf.read(files[0])
            assert len(audio) > sr / 2 and np.isfinite(audio).all(), files[0]
            src = files[0].relative_to(out).as_posix()
            page.append(f'<tr><th>{html.escape(label)}</th><td><audio controls preload="none" src="{src}"></audio></td></tr>')
        page.append('</table>')
    (out / "expressive.html").write_text('\n'.join(page), encoding="utf-8")
    (out / "expressive_settings.json").write_text(json.dumps({
        "tts_model": "k2-fsa/OmniVoice", "seed": 42, "num_step": 32,
        "language": "lt", "reference_transcript": transcript,
        "rvc_index_rate": 0.35, "rvc_clean_audio": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Open {out / 'expressive.html'}", flush=True)


if __name__ == "__main__":
    main()
