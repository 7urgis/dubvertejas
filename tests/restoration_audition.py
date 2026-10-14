#!/usr/bin/env python3
"""Restore short passages from the original Lithuanian episode 149 performance."""
import html
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "media/Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv"
SCENES = [("Narration", 117, 15), ("Conversation", 144, 27), ("Confrontation", 1050, 20)]
CLEANUP = "highpass=f=70,afftdn=nr=6:nf=-45:tn=1"


def run(command):
    subprocess.run(command, check=True)


def main():
    out = ROOT / "output/restoration_audition"
    out.mkdir(parents=True, exist_ok=True)
    variants = [("original", "Original Lithuanian mix"),
                ("restored", "Original mix, gentle noise reduction"),
                ("vocals", "Demucs speech separation"),
                ("vocals_restored", "Separated speech, gentle noise reduction")]
    page = ['<!doctype html><html lang="en"><meta charset="utf-8">',
            '<title>Original Lithuanian restoration</title>',
            '<style>body{font:18px system-ui;max-width:1100px;margin:40px auto;padding:16px}td,th{padding:8px;text-align:left}audio{width:320px}</style>',
            '<h1>Original Lithuanian restoration</h1><p>Actual episode 149 performance: original words, pronunciation, pauses and timing. No TTS or voice conversion.</p>',
            '<p>Gentle restoration uses a 70 Hz high-pass filter and 6 dB spectral noise reduction. Demucs reduces music and effects, but may retain other voices or introduce artifacts. Separated clips are speech-only listening tests, not final episode mixes.</p>',
            '<p>Playback copies use constant gain toward the same RMS level, capped below clipping. No compression, pitch changes or time stretching.</p>']
    report = []
    for number, (label, start, duration) in enumerate(SCENES, 1):
        print(f"Restoring {label}: {start}s, {duration}s", flush=True)
        folder = out / f"scene_{number}"
        folder.mkdir(exist_ok=True)
        original = folder / "original.wav"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-i", str(SOURCE),
             "-t", str(duration), "-map", "0:0", "-ar", "44100", "-ac", "2", str(original)])
        if abs(sf.info(original).duration - duration) >= 0.02:
            raise ValueError(f"Original Lithuanian track does not cover scene at {start}s")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(original),
             "-af", CLEANUP, str(folder / "restored.wav")])
        run([sys.executable, "-m", "demucs", "-n", "htdemucs", "--two-stems", "vocals",
             "--other-method", "none", "--shifts", "2", "--segment", "7", "--float32",
             "--clip-mode", "none", "-d", "cuda", "-o", str(folder / "separated"), str(original)])
        separated = folder / "separated/htdemucs/original/vocals.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(separated),
             "-ar", "44100", "-ac", "2", str(folder / "vocals.wav")])
        run(["ffmpeg", "-v", "error", "-y", "-i", str(separated),
             "-af", CLEANUP, "-ar", "44100", "-ac", "2", str(folder / "vocals_restored.wav")])
        page.append(f'<h2>{html.escape(label)} — {int(start)//60:02d}:{int(start)%60:02d}, {duration} seconds</h2><table>')
        for name, description in variants:
            audio, sr = sf.read(folder / f"{name}.wav")
            assert sr == 44100 and abs(len(audio) / sr - duration) < 0.02
            assert np.isfinite(audio).all() and np.max(np.abs(audio)) > 0.001
            rms = float(np.sqrt(np.mean(audio ** 2)))
            gain = min(10 ** (-22 / 20) / rms, 0.95 / float(np.max(np.abs(audio))))
            audio *= gain
            clip = folder / f"{name}_listen.wav"
            sf.write(clip, audio, sr)
            assert np.max(np.abs(audio)) <= 0.950001
            report.append({"scene": number, "variant": name, "gain_db": 20 * np.log10(gain)})
            src = clip.relative_to(out).as_posix()
            page.append(f'<tr><th>{html.escape(description)}</th><td><audio controls preload="none" src="{src}"></audio></td></tr>')
        page.append('</table>')
    (out / "index.html").write_text('\n'.join(page), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps({
        "source": str(SOURCE), "stream": 0, "scenes": SCENES, "cleanup": CLEANUP,
        "separation": "htdemucs, shifts=2, segment=7", "playback_gains": report,
    }, indent=2), encoding="utf-8")
    print(f"All 12 samples verified. Open {out / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
