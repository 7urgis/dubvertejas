#!/usr/bin/env python3
"""
extract_vocals.py
Extracts dialogue/vocals from vintage audio/video tracks using Demucs (htdemucs).
Strips background music and sound effects to produce clean speech for RVC dataset training.
"""

import os
import sys
import argparse
import subprocess

def extract_vocals(input_audio: str, output_dir: str, model: str = "htdemucs"):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Running Demucs ({model}) on {input_audio}...")
    cmd = [
        "demucs",
        "-n", model,
        "--two-stems", "vocals",
        "-d", "cuda",
        "-o", output_dir,
        input_audio
    ]
    subprocess.run(cmd, check=True)
    print(f"Demucs separation complete in: {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Extract clean speech vocals using Demucs.")
    parser.add_argument("--input", required=True, help="Input audio or video file.")
    parser.add_argument("--output-dir", default="data/demucs_output", help="Output directory.")
    parser.add_argument("--model", default="htdemucs", help="Demucs model architecture.")
    args = parser.parse_args()

    extract_vocals(args.input, args.output_dir, model=args.model)

if __name__ == "__main__":
    main()
