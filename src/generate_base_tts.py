#!/usr/bin/env python3
"""
generate_base_tts.py
Generates base dialogue audio with 100% native Lithuanian stress and cadence
using Microsoft Neural TTS (lt-LT-LeonasNeural via edge-tts).
Converts all synthesized lines to 40kHz mono WAV to match RVC requirements.
"""

import os
import sys
import json
import asyncio
import argparse
import subprocess
import edge_tts

async def synthesize_line(text: str, out_wav: str, voice: str = "lt-LT-LeonasNeural", sample_rate: int = 40000):
    tmp_mp3 = out_wav + ".tmp.mp3"
    try:
        communicate = edge_tts.Communicate(text, voice=voice)
        await communicate.save(tmp_mp3)
        # Convert to target sample rate mono WAV
        cmd = [
            "ffmpeg", "-y", "-i", tmp_mp3,
            "-ar", str(sample_rate), "-ac", "1",
            out_wav
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    finally:
        if os.path.exists(tmp_mp3):
            os.remove(tmp_mp3)

async def generate_all_lines(json_path: str, output_dir: str, voice: str = "lt-LT-LeonasNeural"):
    os.makedirs(output_dir, exist_ok=True)
    with open(json_path, "r", encoding="utf-8") as f:
        dialogue = json.load(f)

    print(f"Generating {len(dialogue)} base dialogue lines using voice '{voice}'...")
    for i, item in enumerate(dialogue):
        idx = item["idx"]
        text = item["lt"].strip()
        out_wav = os.path.join(output_dir, f"line_{idx:03d}.wav")

        if os.path.exists(out_wav):
            continue

        await synthesize_line(text, out_wav, voice=voice)
        if (i + 1) % 15 == 0 or (i + 1) == len(dialogue):
            print(f"  Progress: {i + 1}/{len(dialogue)} synthesized.")

    print(f"All base audio lines ready in: {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Generate base Lithuanian TTS audio lines.")
    parser.add_argument("--json", required=True, help="Path to clean translated JSON subtitles.")
    parser.add_argument("--out-dir", required=True, help="Directory to save base WAV files.")
    parser.add_argument("--voice", default="lt-LT-LeonasNeural", help="Edge TTS voice model.")
    args = parser.parse_args()

    asyncio.run(generate_all_lines(args.json, args.out_dir, voice=args.voice))

if __name__ == "__main__":
    main()
