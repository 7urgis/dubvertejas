#!/usr/bin/env python3
"""
mix_and_remux.py
Studio sound engineering and multiplexing module:
1. Places converted dialogue clips onto the exact millisecond timeline.
2. Resolves overlapping speech lines smoothly.
3. Performs Sidechain Compression Ducking against background Japanese audio (BGM/SFX).
4. Remuxes video, audio streams, and subtitles into a pristine MKV container via mkvmerge.
"""

import os
import sys
import json
import argparse
import subprocess
from itertools import groupby
import numpy as np
import soundfile as sf
import librosa

def assemble_vocals_timeline(json_path: str, rvc_folder: str, out_vocals_flac: str, total_seconds: float = 1482.0, sr: int = 44100, fit_timing: bool = False):
    with open(json_path, "r", encoding="utf-8") as f:
        dialogue = json.load(f)
    dialogue.sort(key=lambda item: float(item["start_sec"]))
    if fit_timing:
        # A single narrator reads simultaneous subtitle entries in sequence.
        groups = [list(items) for _, items in groupby(dialogue, key=lambda item: float(item["start_sec"]))]
        for number, items in enumerate(groups):
            if len(items) < 2:
                continue
            start = float(items[0]["start_sec"])
            end = min(float(item["end_sec"]) for item in items)
            if number + 1 < len(groups):
                end = min(end, float(groups[number + 1][0]["start_sec"]))
            if end <= start:
                raise ValueError(f"Invalid simultaneous subtitle timing at {start}")
            for offset, item in enumerate(items):
                item["start_sec"] = start + offset * (end - start) / len(items)

    total_samples = int(total_seconds * sr)
    canvas = np.zeros(total_samples, dtype=np.float32)

    print(f"Assembling {len(dialogue)} dialogue lines on {total_seconds/60:.1f}m timeline...")
    last_end = 0.0
    placed = 0

    for number, item in enumerate(dialogue):
        idx = item["idx"]
        # Look for matching file: line_{idx:03d}_output.wav or line_{idx:03d}.wav
        candidates = [
            f for f in os.listdir(rvc_folder)
            if f in (f"line_{idx:03d}.wav", f"line_{idx:03d}_output.wav")
        ]
        if not candidates:
            if fit_timing:
                raise FileNotFoundError(f"Missing dialogue audio for line {idx}")
            print(f"  Warning: Missing audio for line #{idx} ({item['lt']})")
            continue
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous audio for line {idx}: {candidates}")

        fpath = os.path.join(rvc_folder, candidates[0])
        wav, file_sr = sf.read(fpath)
        if len(wav.shape) > 1:
            wav = wav[:, 0]

        if file_sr != sr:
            wav = librosa.resample(wav, orig_sr=file_sr, target_sr=sr)

        start_time = float(item["start_sec"])
        if fit_timing:
            # ponytail: keep natural pauses until the next line; use scene alignment for tighter lip sync.
            limit = (float(dialogue[number + 1]["start_sec"])
                     if number + 1 < len(dialogue) else float(item["end_sec"]))
            available = min(limit, total_seconds) - start_time
            if available <= 0:
                raise ValueError(f"No timeline space for line {idx}")
            if len(wav) / sr > available:
                rate = len(wav) / sr / available
                print(f"  Fitting line #{idx} to timeline: {rate:.2f}x tempo")
                wav = librosa.effects.time_stretch(wav, rate=rate)
                wav = wav[:int(available * sr)]
        elif start_time < last_end:
            start_time = last_end + 0.3

        duration = len(wav) / sr
        last_end = start_time + duration

        start_sample = int(start_time * sr)
        end_sample = start_sample + len(wav)

        if end_sample <= len(canvas):
            canvas[start_sample:end_sample] += wav.astype(np.float32)
            placed += 1
        elif start_sample < len(canvas):
            avail = len(canvas) - start_sample
            canvas[start_sample:] += wav[:avail].astype(np.float32)
            placed += 1

    peak = np.max(np.abs(canvas))
    if peak > 0:
        canvas = canvas / peak * 0.95
        print(f"Normalized vocal track (peak: 0.95, placed: {placed}/{len(dialogue)})")

    sf.write(out_vocals_flac, canvas, sr)
    print(f"Saved vocal track to {out_vocals_flac}")

def sidechain_duck_mix(bg_audio: str, vocals_audio: str, out_mixed_flac: str):
    print("Mixing vocals with background audio (Sidechain Ducking)...")
    filter_str = (
        "[1:a]aformat=channel_layouts=stereo:sample_rates=44100[voice];"
        "[0:a]aformat=channel_layouts=stereo:sample_rates=44100[bg];"
        "[voice]asplit=2[v1][sc];"
        "[bg][sc]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350[ducked_bg];"
        "[v1]volume=1.3[v_loud];"
        "[v_loud][ducked_bg]amix=inputs=2:duration=first:dropout_transition=0,volume=1.25[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_audio,
        "-i", vocals_audio,
        "-filter_complex", filter_str,
        "-map", "[out]", "-c:a", "flac", out_mixed_flac
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"Mixed audio track ready: {out_mixed_flac}")

def remux_mkv(video_source: str, mixed_audio: str, output_mkv: str, track_name: str = "Lietuvių k. (Hibridinis RVC - 1990s TV Balsas + Tobulas Kirčiavimas)"):
    print(f"Muxing final MKV video container: {output_mkv}...")
    cmd = [
        "mkvmerge", "-o", output_mkv,
        "--video-tracks", "1",
        "--no-audio",
        "--no-subtitles",
        video_source,
        "--audio-tracks", "0",
        "--track-name", f"0:{track_name}",
        "--language", "0:lit",
        "--default-track-flag", "0:yes",
        mixed_audio,
        "--audio-tracks", "0",
        "--track-name", "0:Lietuvių k. (Originalus 1990s TV Įrašas)",
        "--language", "0:lit",
        "--default-track-flag", "0:no",
        "--no-video",
        "--no-subtitles",
        video_source,
        "--audio-tracks", "2",
        "--track-name", "2:Japonų k. (Originalus Mono)",
        "--language", "2:jpn",
        "--default-track-flag", "2:no",
        "--no-video",
        "--no-subtitles",
        video_source,
        "--subtitle-tracks", "6,7,8,9,10",
        "--no-video",
        "--no-audio",
        video_source
    ]
    subprocess.run(cmd, check=True)
    print(f"\nSUCCESS! Remastered MKV created at: {output_mkv}")

def main():
    parser = argparse.ArgumentParser(description="Assemble timeline, duck mix, and remux MKV.")
    parser.add_argument("--json", required=True, help="Path to clean translated JSON subtitles.")
    parser.add_argument("--rvc-folder", required=True, help="Folder containing converted RVC clips.")
    parser.add_argument("--bg-audio", required=True, help="Background Japanese / BGM audio file.")
    parser.add_argument("--video", required=True, help="Source MKV video file.")
    parser.add_argument("--output", required=True, help="Destination remastered MKV path.")
    parser.add_argument("--temp-dir", default="temp", help="Directory for intermediate audio stems.")
    parser.add_argument("--fit-timing", action="store_true", help="Keep subtitle starts; speed up lines only when needed to avoid overlaps.")
    parser.add_argument("--track-name", default="Lietuvių k. (Hibridinis RVC - 1990s TV Balsas + Tobulas Kirčiavimas)")
    args = parser.parse_args()

    os.makedirs(args.temp_dir, exist_ok=True)
    vocals_flac = os.path.join(args.temp_dir, "vocals_full.flac")
    mixed_flac = os.path.join(args.temp_dir, "mixed_final.flac")

    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", args.video,
    ], capture_output=True, text=True, check=True)
    assemble_vocals_timeline(args.json, args.rvc_folder, vocals_flac,
                            total_seconds=float(probe.stdout.strip()), fit_timing=args.fit_timing)
    sidechain_duck_mix(args.bg_audio, vocals_flac, mixed_flac)
    remux_mkv(args.video, mixed_flac, args.output, track_name=args.track_name)

if __name__ == "__main__":
    main()
