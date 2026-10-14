#!/usr/bin/env python3
"""Mix separated original dialogue over a Japanese soundtrack, preserving timing."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from faster_whisper.vad import get_speech_timestamps, VadOptions

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mix_and_remux import remux_mkv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocals", required=True)
    parser.add_argument("--bg-audio", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--speech-window", nargs=2, type=float, required=True, metavar=("START", "END"))
    parser.add_argument("--temp-dir", required=True)
    args = parser.parse_args()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", args.video],
                           capture_output=True, text=True, check=True)
    duration = float(probe.stdout.strip())
    start, end = args.speech_window
    if not 0 <= start < end <= duration:
        raise ValueError("Speech window must lie within the video")
    work = Path(args.temp_dir)
    work.mkdir(parents=True, exist_ok=True)
    audio, sr = sf.read(args.vocals, dtype="float32", always_2d=True)
    if sr != 44100 or not np.isfinite(audio).all():
        raise ValueError("Expected finite 44.1 kHz separated audio")
    if len(audio) / sr < end:
        raise ValueError("Separated audio does not cover the speech window")
    # ponytail: VAD excludes non-speech, but cannot distinguish Lithuanian from underlying foreign voices.
    mono = audio.mean(axis=1)
    speech = get_speech_timestamps(resample_poly(mono, 160, 441), VadOptions(
        threshold=0.35, min_silence_duration_ms=350, speech_pad_ms=250))
    mask = np.zeros(len(audio), dtype=np.float32)
    kept = []
    fade = int(sr * 0.01)
    for segment in speech:
        left = max(int(start * sr), int(segment["start"] * sr / 16000))
        right = min(int(end * sr), int(segment["end"] * sr / 16000), len(audio))
        if right <= left:
            continue
        mask[left:right] = 1
        ramp = min(fade, (right - left) // 2)
        if ramp:
            mask[left:left + ramp] = np.linspace(0, 1, ramp)
            mask[right - ramp:right] = np.linspace(1, 0, ramp)
        kept.append({"start": left / sr, "end": right / sr})
    if not kept:
        raise ValueError("No speech detected in the selected window")
    assert not mask[:int(start * sr)].any() and not mask[int(end * sr):].any()
    audio *= mask[:, None]
    peak = float(np.max(np.abs(audio)))
    if peak < 0.001:
        raise ValueError("Separated speech is silent")
    gain = min(2.0, 0.85 / peak)
    voice = np.zeros((round(duration * sr), 2), dtype=np.float32)
    count = min(len(voice), len(audio))
    voice[:count] = audio[:count] * gain
    assert not voice[int(end * sr):].any() and np.max(np.abs(voice)) <= 0.850001
    sf.write(work / "original_dialogue.flac", voice, sr)
    print(f"Retained {len(kept)} speech intervals; original timing unchanged", flush=True)
    filters = (
        f"[0:a]aformat=channel_layouts=stereo:sample_rates=44100,apad=whole_dur={duration}[bg];"
        "[1:a]asplit=2[voice][sc];"
        "[bg][sc]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350[ducked];"
        "[voice]volume=1.3[loud];"
        "[loud][ducked]amix=inputs=2:duration=first:dropout_transition=0,volume=1.25[out]"
    )
    raw = work / "mixed_float.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", args.bg_audio,
                    "-i", str(work / "original_dialogue.flac"), "-filter_complex", filters,
                    "-map", "[out]", "-c:a", "pcm_f32le", str(raw)], check=True)
    mixed_peak = max(float(np.max(np.abs(block))) for block in sf.blocks(raw, blocksize=65536))
    mix_gain = min(1, 0.95 / mixed_peak)
    mixed = work / "mixed_final.flac"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw),
                    "-af", f"volume={mix_gain},apad=whole_dur={duration},atrim=duration={duration}",
                    "-c:a", "flac", str(mixed)], check=True)
    assert abs(sf.info(mixed).duration - duration) < 0.01
    assert max(float(np.max(np.abs(b))) for b in sf.blocks(mixed, blocksize=65536)) < 0.951
    remux_mkv(args.video, str(mixed), args.output,
              track_name="Lietuvių k. (Originalus aktorius + japoniškas fonas)")
    (work / "settings.json").write_text(json.dumps({
        "vocals": args.vocals, "background": args.bg_audio, "speech_window": [start, end],
        "speech_intervals": kept, "voice_gain": gain, "mix_gain": mix_gain,
        "separation": "htdemucs, shifts=2, segment=7", "tts": False, "rvc": False,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
