#!/usr/bin/env python3
"""
batch_rvc.py
Runs batch voice conversion with RVC v2 using Applio core engine.
Transforms the vocal timbre from base TTS to the target voice actor
while preserving exact pitch contour (f0), rhythm, and Lithuanian stress.
"""

import os
import sys
import argparse
import subprocess
import time

def run_rvc_conversion(
    input_folder: str,
    output_folder: str,
    pth_path: str,
    index_path: str,
    applio_dir: str = None,
    f0_method: str = "rmvpe",
    index_rate: float = 0.75,
    protect: float = 0.33,
    pitch: int = 0
):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if applio_dir is None:
        applio_dir = os.path.join(project_root, "tools/Applio")

    applio_python = os.path.join(applio_dir, ".venv/bin/python")
    core_py = os.path.join(applio_dir, "core.py")

    if not os.path.exists(applio_python):
        # Fallback to current python interpreter
        applio_python = sys.executable

    os.makedirs(output_folder, exist_ok=True)

    print("\n" + "="*70)
    print(f"RVC Batch Voice Conversion")
    print(f"Model: {pth_path}")
    print(f"Index: {index_path}")
    print(f"Input: {input_folder}")
    print(f"Output: {output_folder}")
    print("="*70)

    t0 = time.time()
    cmd = [
        applio_python, core_py, "batch-infer",
        "--input-folder", os.path.abspath(input_folder),
        "--output-folder", os.path.abspath(output_folder),
        "--pth-path", os.path.abspath(pth_path),
        "--index-path", os.path.abspath(index_path),
        "--f0-method", f0_method,
        "--index-rate", str(index_rate),
        "--protect", str(protect),
        "--pitch", str(pitch),
        "--clean-audio",
        "--export-format", "WAV"
    ]

    # Applio MUST be run with cwd = applio_dir so its internal predictor model paths resolve
    subprocess.run(cmd, cwd=applio_dir, check=True)
    print(f"\nRVC Batch Conversion finished in {time.time() - t0:.1f}s!")

def main():
    parser = argparse.ArgumentParser(description="Run RVC v2 batch voice conversion.")
    parser.add_argument("--input-folder", required=True, help="Folder containing base WAV clips.")
    parser.add_argument("--output-folder", required=True, help="Folder to save converted WAV clips.")
    parser.add_argument("--pth", required=True, help="Path to trained RVC model checkpoint (.pth).")
    parser.add_argument("--index", required=True, help="Path to trained Faiss index (.index).")
    parser.add_argument("--applio-dir", default=None, help="Path to Applio framework folder.")
    parser.add_argument("--index-rate", type=float, default=0.75, help="Influence of index feature retrieval.")
    args = parser.parse_args()

    run_rvc_conversion(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        pth_path=args.pth,
        index_path=args.index,
        applio_dir=args.applio_dir,
        index_rate=args.index_rate
    )

if __name__ == "__main__":
    main()
