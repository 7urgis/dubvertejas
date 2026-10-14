#!/usr/bin/env python3
"""Generate Lithuanian dialogue using the auditioned OmniVoice reference."""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--reference-text", required=True)
    args = parser.parse_args()
    dialogue = json.loads(Path(args.json).read_text(encoding="utf-8"))
    seen = set()
    for item in dialogue:
        if (not isinstance(item["idx"], int) or item["idx"] in seen
                or not item["lt"].strip()
                or not 0 <= float(item["start_sec"]) < float(item["end_sec"])):
            raise ValueError(f"Invalid dialogue entry: {item}")
        seen.add(item["idx"])
    if not dialogue or not args.reference_text.strip():
        raise ValueError("Dialogue and reference text must not be empty")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(42)
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16
    )
    prompt = model.create_voice_clone_prompt(
        ref_audio=args.reference, ref_text=args.reference_text
    )
    report = []
    for n, item in enumerate(dialogue, 1):
        print(f"[{n}/{len(dialogue)}] #{item['idx']}: {item['lt']}", flush=True)
        audio = model.generate(
            text=item["lt"].strip(), language="lt", voice_clone_prompt=prompt, num_step=32
        )[0]
        if (not np.isfinite(audio).all() or len(audio) < model.sampling_rate / 2
                or np.max(np.abs(audio)) < 0.001):
            raise ValueError(f"Invalid generated speech for line {item['idx']}")
        sf.write(out / f"line_{item['idx']:03d}.wav", audio, model.sampling_rate)
        report.append({"idx": item["idx"], "seconds": len(audio) / model.sampling_rate,
                       "subtitle_seconds": item["end_sec"] - item["start_sec"]})
    (out / "generation.json").write_text(json.dumps({
        "model": "k2-fsa/OmniVoice", "seed": 42, "num_step": 32,
        "reference": args.reference, "reference_text": args.reference_text,
        "lines": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated all {len(dialogue)} lines in {out}", flush=True)


if __name__ == "__main__":
    main()
