#!/usr/bin/env python3
"""
pipeline.py
Master End-to-End Remastering Pipeline for Dubvertejas.

Executes the complete hybrid workflow:
1. Normalizes dialogue subtitles (phonetic Lithuanian numbers/names).
2. Generates base dialogue with 100% native Lithuanian stress (Edge-TTS LeonasNeural).
3. Converts voice timbre to the iconic 1990s TV actor via RVC v2 + Faiss index.
4. Places dialogue on timeline, performs sidechain ducking over original audio, and remuxes into MKV.
"""

import os
import sys
import glob
import argparse
import subprocess
import time

def find_rvc_model_files(model_dir: str):
    pths = [
        f for f in glob.glob(os.path.join(model_dir, "*.pth"))
        if not os.path.basename(f).startswith(("D_", "G_"))
    ]
    if not pths:
        raise FileNotFoundError(f"No trained .pth model found in {model_dir}")
    pths.sort(key=os.path.getmtime, reverse=True)
    pth_path = pths[0]

    indices = glob.glob(os.path.join(model_dir, "*.index"))
    if not indices:
        raise FileNotFoundError(f"No .index Faiss file found in {model_dir}")
    index_path = indices[0]

    return pth_path, index_path

def run_pipeline(
    video_path: str,
    json_path: str,
    output_mkv: str,
    model_dir: str = "models/dbz_actor",
    base_voice: str = "lt-LT-LeonasNeural",
    work_dir: str = "temp",
    bg_audio_path: str = None
):
    project_root = os.path.dirname(os.path.abspath(__file__))
    applio_dir = os.path.join(project_root, "tools/Applio")
    applio_python = os.path.join(applio_dir, ".venv/bin/python")
    if not os.path.exists(applio_python):
        applio_python = sys.executable

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_mkv)), exist_ok=True)

    base_wavs_dir = os.path.join(work_dir, "01_base_tts")
    rvc_wavs_dir = os.path.join(work_dir, "02_rvc_dub")
    vocals_flac = os.path.join(work_dir, "03_vocals_full.flac")
    mixed_flac = os.path.join(work_dir, "04_mixed_final.flac")

    pth_path, index_path = find_rvc_model_files(model_dir)

    print("\n" + "="*75)
    print("DUBVERTEJAS: HYBRID AI VOICE REMASTERING PIPELINE")
    print(f"Video Source : {video_path}")
    print(f"Subtitles    : {json_path}")
    print(f"RVC Model    : {pth_path}")
    print(f"Faiss Index  : {index_path}")
    print(f"Output MKV   : {output_mkv}")
    print("="*75)

    start_total = time.time()

    # Step 1: Extract background audio from video if not provided
    if bg_audio_path is None or not os.path.exists(bg_audio_path):
        bg_audio_path = os.path.join(work_dir, "bg_audio.flac")
        if not os.path.exists(bg_audio_path):
            print("\n[Step 1/4] Extracting Japanese / original background audio from video...")
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-map", "0:2", "-c:a", "flac", bg_audio_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Step 2: Base TTS generation (100% native Lithuanian stress)
    print("\n[Step 2/4] Synthesizing base Lithuanian speech with Edge-TTS...")
    gen_tts_script = os.path.join(project_root, "src/generate_base_tts.py")
    subprocess.run([
        applio_python, gen_tts_script,
        "--json", json_path,
        "--out-dir", base_wavs_dir,
        "--voice", base_voice
    ], check=True)

    # Step 3: Batch RVC voice conversion (Transform timbre into 90s actor)
    print("\n[Step 3/4] Transforming vocal timbre to 90s TV actor via RVC v2...")
    batch_rvc_script = os.path.join(project_root, "src/batch_rvc.py")
    subprocess.run([
        applio_python, batch_rvc_script,
        "--input-folder", base_wavs_dir,
        "--output-folder", rvc_wavs_dir,
        "--pth", pth_path,
        "--index", index_path,
        "--applio-dir", applio_dir
    ], check=True)

    # Step 4: Assemble timeline, sidechain duck mix, and remux MKV
    print("\n[Step 4/4] Assembling timeline, ducking background audio, and remuxing MKV...")
    mix_script = os.path.join(project_root, "src/mix_and_remux.py")
    subprocess.run([
        applio_python, mix_script,
        "--json", json_path,
        "--rvc-folder", rvc_wavs_dir,
        "--bg-audio", bg_audio_path,
        "--video", video_path,
        "--output", output_mkv,
        "--temp-dir", work_dir
    ], check=True)

    elapsed = time.time() - start_total
    print("\n" + "="*75)
    print(f"PIPELINE COMPLETED SUCCESSFULLY IN {elapsed/60:.2f} MINUTES!")
    print(f"Final Remastered Episode: {output_mkv}")
    print("="*75)

def main():
    parser = argparse.ArgumentParser(description="Run complete Dubvertejas remastering pipeline.")
    parser.add_argument("--video", required=True, help="Input video MKV file.")
    parser.add_argument("--json", required=True, help="Input clean translated subtitles JSON.")
    parser.add_argument("--output", default="output/remastered.mkv", help="Output remastered MKV path.")
    parser.add_argument("--model-dir", default="models/dbz_actor", help="Folder with trained RVC .pth and .index.")
    parser.add_argument("--voice", default="lt-LT-LeonasNeural", help="Base TTS voice.")
    parser.add_argument("--work-dir", default="temp", help="Working directory for intermediate files.")
    parser.add_argument("--bg-audio", default=None, help="Optional extracted background audio track.")
    args = parser.parse_args()

    run_pipeline(
        video_path=args.video,
        json_path=args.json,
        output_mkv=args.output,
        model_dir=args.model_dir,
        base_voice=args.voice,
        work_dir=args.work_dir,
        bg_audio_path=args.bg_audio
    )

if __name__ == "__main__":
    main()
