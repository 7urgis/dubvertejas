#!/usr/bin/env python3
"""
slice_dataset.py
Slices a clean vocal track into short dialogue segments (1.5s - 10s)
for training RVC v2 voice models.
Normalizes audio to 40kHz mono WAV.
"""

import os
import sys
import argparse
import numpy as np
import soundfile as sf
import librosa

def slice_vocal_track(
    input_wav: str,
    output_dir: str,
    target_sr: int = 40000,
    top_db: float = 30.0,
    min_len_sec: float = 1.2,
    max_len_sec: float = 10.0
):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Loading {input_wav}...")
    audio, sr = librosa.load(input_wav, sr=target_sr, mono=True)

    print(f"Detecting non-silent intervals (top_db={top_db})...")
    intervals = librosa.effects.split(audio, top_db=top_db, frame_length=2048, hop_length=512)
    print(f"Found {len(intervals)} candidate speech segments.")

    count = 0
    total_duration = 0.0

    for i, (start_idx, end_idx) in enumerate(intervals):
        seg = audio[start_idx:end_idx]
        dur = len(seg) / target_sr

        if min_len_sec <= dur <= max_len_sec:
            out_file = os.path.join(output_dir, f"clip_{count:04d}.wav")
            # Peak normalize
            peak = np.max(np.abs(seg))
            if peak > 0:
                seg = seg / peak * 0.95
            sf.write(out_file, seg, target_sr)
            count += 1
            total_duration += dur

    print(f"Exported {count} clean training clips ({total_duration/60:.2f} mins total) to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Slice clean speech for RVC training dataset.")
    parser.add_argument("--input", required=True, help="Input clean vocal WAV file.")
    parser.add_argument("--output-dir", required=True, help="Directory to save sliced WAV clips.")
    parser.add_argument("--top-db", type=float, default=30.0, help="Silence threshold dB.")
    args = parser.parse_args()

    slice_vocal_track(args.input, args.output_dir, top_db=args.top_db)

if __name__ == "__main__":
    main()
