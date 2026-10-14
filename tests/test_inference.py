#!/usr/bin/env python3
"""
test_inference.py
Quick end-to-end sanity check for the RVC inference pipeline in dubvertejas.
Synthesizes a short test sentence with Edge-TTS and converts it with the trained model.
"""

import os
import sys
import asyncio
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.generate_base_tts import synthesize_line
from src.batch_rvc import run_rvc_conversion

async def test_sanity():
    out_dir = os.path.join(PROJECT_ROOT, "temp/sanity_test")
    os.makedirs(out_dir, exist_ok=True)
    
    base_wav = os.path.join(out_dir, "base_test.wav")
    text = "Kova tarp Pikolo ir roboto numeris septyniolika jau prasidėjo."
    
    print(f"1. Synthesizing base TTS: \"{text}\"...")
    await synthesize_line(text, base_wav)
    print("   Base WAV created successfully.")
    
    pth = os.path.join(PROJECT_ROOT, "models/dbz_actor/dbz_actor_100e_2400s.pth")
    index = os.path.join(PROJECT_ROOT, "models/dbz_actor/dbz_actor.index")
    rvc_out = os.path.join(out_dir, "rvc_output")
    
    print("2. Converting timbre to 90s actor...")
    run_rvc_conversion(
        input_folder=out_dir,
        output_folder=rvc_out,
        pth_path=pth,
        index_path=index,
        applio_dir=os.path.join(PROJECT_ROOT, "tools/Applio")
    )
    print("   Sanity test passed! Converted audio ready in:", rvc_out)

if __name__ == "__main__":
    asyncio.run(test_sanity())
