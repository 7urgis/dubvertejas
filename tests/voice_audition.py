#!/usr/bin/env python3
"""Generate a five-line listening comparison. Run with Applio's Python."""
import asyncio
import html
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.generate_base_tts import synthesize_line
from pipeline import find_rvc_model_files

LINES = [
    ("Narration", "Pagaliau Gokas atgavo jėgas."),
    ("Question", "Kaip gaila. Kokia nesėkmė, ar ne?"),
    ("Excitement", "Cha! Aš dar tik pradedu!"),
    ("Anger", "Ne! Aš tau niekada neatleisiu!"),
    ("Quiet", "Tačiau jau per vėlu."),
]
VARIANTS = [
    ("current", "Current: index 0.75, cleaning on", "0.75", True),
    ("no_clean", "Index 0.75, cleaning off", "0.75", False),
    ("low_index", "Index 0.35, cleaning off", "0.35", False),
    ("no_index", "Index 0, cleaning off", "0", False),
]


async def main():
    out = ROOT / "output/voice_audition"
    base = out / "base"
    base.mkdir(parents=True, exist_ok=True)
    # Fresh synthesis avoids reusing an earlier experiment's cached speech.
    for i, (_, text) in enumerate(LINES, 1):
        print(f"Synthesizing {i}/{len(LINES)}: {text}", flush=True)
        await synthesize_line(text, str(base / f"line_{i:03d}.wav"))
    pth, index = find_rvc_model_files(str(ROOT / "models/dbz_actor"))
    applio = ROOT / "tools/Applio"
    for name, label, rate, clean in VARIANTS:
        target = out / name
        target.mkdir(exist_ok=True)
        print(label, flush=True)
        command = [str(applio / ".venv/bin/python"), "core.py", "batch-infer",
                   "--input-folder", str(base), "--output-folder", str(target),
                   "--pth-path", pth, "--index-path", index,
                   "--index-rate", rate, "--protect", "0.33",
                   "--pitch", "0", "--f0-method", "rmvpe", "--export-format", "WAV"]
        if clean:
            command.append("--clean-audio")
        subprocess.run(command, cwd=applio, check=True)
    groups = [("base", "Base TTS before conversion")] + [(v[0], v[1]) for v in VARIANTS]
    page = ['<!doctype html><meta charset="utf-8"><title>Voice audition</title>',
            '<style>body{font:18px system-ui;max-width:1000px;margin:40px auto;padding:16px}td,th{padding:8px;text-align:left}audio{width:280px}</style>',
            '<h1>Voice audition</h1><p>Compare the same line across settings. Listen for expression, actor resemblance, consonants and metallic artifacts. These labels describe intended delivery; neutral TTS receives no emotion instruction.</p>']
    human_source = out / "human_input/reference.wav"
    human_result = out / "human_rvc/reference_output.wav"
    if human_source.exists() and human_result.exists():
        page.append('<h2>Human speech through the same model</h2><p>The existing actor reference, then RVC at index 0.35 with cleaning off. This is a diagnostic comparison, not an independent evaluation: the clip may have been used in training and may contain background sound.</p>')
        for clip, label in [(human_source, "Actor reference"), (human_result, "Actor reference through RVC")]:
            page.append(f'<p>{label}</p><audio controls preload="none" src="{clip.relative_to(out).as_posix()}"></audio>')
    for i, (kind, text) in enumerate(LINES, 1):
        page.append(f'<h2>{html.escape(kind)}</h2><p lang="lt">{html.escape(text)}</p><table>')
        for folder, label in groups:
            files = sorted((out / folder).glob(f"line_{i:03d}*.wav"))
            assert len(files) == 1, f"Expected one output for {folder}, line {i}: {files}"
            assert files[0].stat().st_size > 44, f"Empty audio: {files[0]}"
            src = html.escape(files[0].relative_to(out).as_posix(), quote=True)
            page.append(f'<tr><th>{html.escape(label)}</th><td><audio controls preload="none" src="{src}"></audio></td></tr>')
        page.append('</table>')
    (out / "index.html").write_text('\n'.join(page), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps({"lines": LINES, "variants": VARIANTS, "model": pth}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Open {out / 'index.html'}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
