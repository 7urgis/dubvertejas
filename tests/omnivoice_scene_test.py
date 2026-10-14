#!/usr/bin/env python3
"""Render episode 149, 15:50–17:40, using transcribed LT words and local references."""
import html
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf
import torch
from omnivoice import OmniVoice

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.mix_and_remux import assemble_vocals_timeline

# Compared original/separated Whisper transcripts against the English scene meaning.
# Uncertain reconstructions remain explicit in the review table, never in spoken text.
LINES = [
    (953.58, 954.92, "Krilinai, ką mums daryti?", ""),
    (955.76, 956.94, "Iš kur aš galiu žinoti?", ""),
    (958.66, 965.74, "Jei tas pabaisa Selas įsiurbs kiborgus, visos mūsų viltys žlugs. Pražus visa Žemės planeta.", "ASR misrecognized Selas and įsiurbs; reconstructed using scene context."),
    (968.32, 969.10, "Prakeikimas!", ""),
    (971.46, 973.44, "Krilinai, tau skambina Bulma.", ""),
    (974.19, 975.04, "Man?", ""),
    (976.17, 978.34, "Ji sako, kad sukūrė ginklą prieš kiborgus.", "ASR unclear around ginklą; original wording needs listener verification."),
    (979.72, 980.89, "Kas? Ką pasakė?", "Opening interjection unclear in both transcripts; needs listener verification."),
    (983.63, 988.04, "Taip, septynioliktojo ir aštuonioliktojo tipo kiborgai turi silpnąją vietą.", "Numbers expanded for pronunciation."),
    (988.20, 989.82, "Tai skubaus išjungimo grandis.", "ASR says sujungimo; English specifies emergency shutdown. išjungimo is a provisional correction."),
    (989.82, 993.24, "Nutraukę tą grandį, lengvai sunaikinsime kiborgus.", ""),
    (993.49, 995.80, "Aš ką tik sukūriau nuotolinio valdymo pultą.", ""),
    (1001.46, 1004.42, "Krilinai, paklausk, ar mes galėsime nukauti kiborgus?", ""),
    (1006.40, 1009.74, "Bulma, ar gali tuoj pat atgabenti pultą čionai?", "ASR says galiu; corrected person from scene context."),
    (1010.14, 1012.34, "Pikolas jau kaunasi su kiborgais.", ""),
    (1014.36, 1015.90, "Gerai, tuoj atlėksiu.", ""),
    (1017.36, 1022.42, "Puiku. Jei sunaikinsime septynioliktąjį kiborgą, Selas netaps visagalis.", "Number expanded for pronunciation."),
    (1037.25, 1038.88, "Sunaikinsime juos visus?", ""),
    (1039.20, 1040.86, "Krilinai, kas tau?", ""),
    (1043.27, 1044.13, "Nieko.", ""),
    (1045.59, 1047.68, "Aš išskrendu.", ""),
    (1048.17, 1049.28, "Pasirūpinkit vaiku.", ""),
    (1050.19, 1051.48, "Pasirūpinti tavo vaiku?", ""),
    (1051.60, 1053.82, "Kaip tu gali palikti savo mažylį vieną?", ""),
    (1055.22, 1058.53, "Paleisk! Visai Žemės planetai gresia didžiulis pavojus.", ""),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(ROOT / "output/omnivoice_149_1550_1740"))
    parser.add_argument("--shared-references", action="store_true")
    parser.add_argument("--natural-timing", action="store_true")
    parser.add_argument("--candidates", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--steps", type=int, choices=(32, 64), default=32)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--start", type=float, default=950)
    parser.add_argument("--duration", type=float, default=110)
    parser.add_argument("--reuse-preview", action="store_true")
    args = parser.parse_args()
    if args.start < 0 or args.duration <= 0:
        raise ValueError("Invalid render window")
    lines = LINES
    input_entries = []
    if args.transcript:
        input_entries = json.loads(args.transcript.read_text())
        lines = [(x["start_sec"], x["end_sec"], x["lt"], x.get("review_note", "")) for x in input_entries]
    if not lines or any(not text.strip() or not args.start <= start < end <= args.start + args.duration
                        for start, end, text, _ in lines):
        raise ValueError("Invalid transcript text or timing")
    if any(lines[i][0] >= lines[i + 1][0] for i in range(len(lines) - 1)):
        raise ValueError("Transcript must have strictly increasing start times")
    out = Path(args.out_dir).resolve()
    baseline = ROOT / "output/omnivoice_149_1550_1740"
    if out == baseline and (args.transcript or args.start != 950 or args.duration != 110 or args.shared_references or args.natural_timing or args.candidates != 1 or args.steps != 32):
        raise ValueError("Use a separate --out-dir to preserve the accepted preview")
    references = out / "references"
    generated = out / "generated"
    references.mkdir(parents=True, exist_ok=True)
    generated.mkdir(exist_ok=True)
    source = ROOT / "media/Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv"
    stem = ROOT / "temp/ep149_original_jp/separated/htdemucs/original_lt/vocals.wav"
    entries = []
    preview_entries = json.loads((baseline / "transcript.json").read_text()) if args.reuse_preview else []
    for i, (start, end, text, note) in enumerate(lines):
        # Short replies borrow adjacent complete speech, without crossing long pauses.
        left, right = i, i
        while lines[right][1] - lines[left][0] < 3:
            choices = []
            if left > 0 and lines[left][0] - lines[left - 1][1] < 4:
                choices.append((lines[right][1] - lines[left - 1][0], left - 1, right))
            if right + 1 < len(lines) and lines[right + 1][0] - lines[right][1] < 4:
                choices.append((lines[right + 1][1] - lines[left][0], left, right + 1))
            choices = [c for c in choices if c[0] <= 9.5]
            if not choices:
                break
            _, left, right = min(choices)
        ref_start = lines[left][0] - 0.12
        ref_end = lines[right][1] + 0.12
        clip = references / f"line_{i + 1:03d}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ref_start), "-i", str(stem),
                        "-t", str(ref_end - ref_start), "-af", "highpass=f=70,afftdn=nr=6:nf=-45",
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_f32le", str(clip)], check=True)
        audio, sr = sf.read(clip)
        peak = float(np.max(np.abs(audio)))
        assert peak > 0.001 and np.isfinite(audio).all()
        sf.write(clip, audio * min(1, 0.85 / peak), sr)
        entries.append({"idx": i + 1, "start_sec": start - args.start, "end_sec": end - args.start,
                        "lt": text, "review_note": note, "reference": str(clip),
                        "reference_text": " ".join(row[2] for row in lines[left:right + 1]),
                        "reference_start": ref_start, "reference_end": ref_end})
    if args.reuse_preview:
        for item, original in zip(entries, input_entries):
            if "preview_idx" in original:
                old = preview_entries[original["preview_idx"] - 1]
                item.update(reference=old["reference"], reference_text=old["reference_text"],
                            reference_start=old["reference_start"], reference_end=old["reference_end"],
                            preview_idx=old["idx"])
    (out / "transcript.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.shared_references:
        original_entries = json.loads((baseline / "transcript.json").read_text())
        anchors = {
            "calm": (ROOT / "data/samples/reference_90s_actor.flac", "Selas netrukus taps visagalis."),
            "question": (Path(original_entries[0]["reference"]), original_entries[0]["reference_text"]),
            "urgent": (Path(original_entries[24]["reference"]), original_entries[24]["reference_text"]),
        }
        for style, (clip, text) in anchors.items():
            shared = references / f"shared_{style}{clip.suffix}"
            shutil.copyfile(clip, shared)
            anchors[style] = (shared, text)
        for item in entries:
            style = ("urgent" if item["idx"] in (3, 4, 25) else
                     "question" if "?" in item["lt"] else "calm")
            reference, text = anchors[style]
            item.update(reference=str(reference), reference_text=text, reference_style=style,
                        reference_start=None, reference_end=None)
        (out / "transcript.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)
    prompts = {}
    selections = []
    for item in entries:
        saved = generated / f"line_{item['idx']:03d}.wav"
        if item.get("preview_idx"):
            shutil.copyfile(baseline / "generated" / f"line_{item['preview_idx']:03d}.wav", saved)
            selections.append({"idx": item["idx"], "reused_preview_idx": item["preview_idx"]})
            print(f"Reused accepted preview line {item['preview_idx']}", flush=True)
            continue
        if saved.exists():
            data, _ = sf.read(saved)
            if len(data) and np.isfinite(data).all() and np.max(np.abs(data)) > 0.001:
                selections.append({"idx": item["idx"], "resumed": True})
                print(f"Reused completed generation {item['idx']}", flush=True)
                continue
        print(f"Generating {item['idx']}/{len(entries)}: {item['lt']}", flush=True)
        if item["reference"] not in prompts:
            prompts[item["reference"]] = model.create_voice_clone_prompt(ref_audio=item["reference"], ref_text=item["reference_text"])
        prompt = prompts[item["reference"]]
        options = {} if args.natural_timing else {"duration": max(1.3 if item["lt"] == "Prakeikimas!" else 0, item["end_sec"] - item["start_sec"])}
        available = (entries[item["idx"]]["start_sec"] if item["idx"] < len(entries) else args.duration) - item["start_sec"]
        candidates = []
        for candidate in range(args.candidates):
            seed = 42 + item["idx"] + candidate * 1000
            torch.manual_seed(seed)
            audio = model.generate(text=item["lt"], language="lt", voice_clone_prompt=prompt,
                                   num_step=args.steps, **options)[0]
            if len(audio) <= model.sampling_rate / 4 or not np.isfinite(audio).all() or np.max(np.abs(audio)) <= 0.001:
                raise ValueError(f"Invalid generated speech: line {item['idx']}, candidate {candidate}")
            seconds = len(audio) / model.sampling_rate
            path = generated / f"candidate_{item['idx']:03d}_{candidate + 1}.wav"
            sf.write(path, audio, model.sampling_rate)
            candidates.append((max(1, seconds / available), candidate, path, seconds, seed))
        # ponytail: choose minimal timing distortion; a listener must judge acting and artifacts.
        _, chosen, path, seconds, seed = min(candidates)
        shutil.copyfile(path, generated / f"line_{item['idx']:03d}.wav")
        selections.append({"idx": item["idx"], "candidate": chosen + 1, "seed": seed,
                           "seconds": seconds, "available_seconds": available,
                           "selection_rule": "minimum required speed-up; first candidate wins ties"})
    del model, prompts
    torch.cuda.empty_cache()
    voice = out / "ai_voice.flac"
    assemble_vocals_timeline(str(out / "transcript.json"), str(generated), str(voice), total_seconds=args.duration, fit_timing=True)
    jp = out / "japanese.flac"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(args.start), "-i", str(source),
                    "-t", str(args.duration), "-map", "0:2", "-ar", "44100", "-ac", "2", str(jp)], check=True)
    # Only newly generated speech and Japanese audio enter this mix.
    filters = ("[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[v][sc];"
               "[0:a][sc]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=350[bg];"
               "[v]volume=1.3[loud];[loud][bg]amix=inputs=2:duration=first:dropout_transition=0,volume=1.25[out]")
    raw = out / "mixed_float.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(jp), "-i", str(voice),
                    "-filter_complex", filters, "-map", "[out]", "-c:a", "pcm_f32le", str(raw)], check=True)
    peak = max(float(np.max(np.abs(b))) for b in sf.blocks(raw, blocksize=65536))
    mixed = out / "mixed.flac"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    f"volume={min(1, 0.95 / peak)},apad=whole_dur={args.duration},atrim=duration={args.duration}", str(mixed)], check=True)
    video = out / ("Dragon.Ball.Z.149.LT-OmniVoice.mp4" if args.transcript else "Dragon.Ball.Z.149.1550-1740.LT-OmniVoice.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(args.start), "-i", str(source),
                    "-i", str(mixed), "-t", str(args.duration), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac",
                    "-b:a", "256k", "-movflags", "+faststart", str(video)], check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                      "-of", "json", str(video)], check=True, capture_output=True, text=True).stdout)
    assert abs(float(probe["format"]["duration"]) - args.duration) < 0.1
    assert len([s for s in probe["streams"] if s["codec_type"] == "audio"]) == 1
    def timestamp(seconds):
        milliseconds = round(seconds * 1000)
        return f"{milliseconds // 3600000:02d}:{milliseconds // 60000 % 60:02d}:{milliseconds // 1000 % 60:02d}.{milliseconds % 1000:03d}"
    captions = ["WEBVTT\n"]
    for item in entries:
        captions.append(f"{timestamp(item['start_sec'])} --> {timestamp(item['end_sec'])}\n{item['lt']}\n")
    (out / "transcript.vtt").write_text('\n'.join(captions), encoding="utf-8")
    page = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>OmniVoice scene test</title>',
            '<style>body{font:18px system-ui;max-width:1100px;margin:40px auto;padding:16px}video{width:100%}td,th{padding:8px;text-align:left}audio{width:280px}</style>',
            f'<h1>Episode 149 — {"full episode" if args.transcript else "15:50–17:40"}</h1><p>Fresh OmniVoice speech, original Lithuanian wording reconstructed from ASR, local actor references, Japanese soundtrack. No RVC or recorded Lithuanian audio in the mix.</p>',
            f'<video controls src="{video.name}"><track kind="subtitles" src="transcript.vtt" srclang="lt" label="Lietuvių"></video>',
            '<h2>Generated voice alone</h2><audio controls src="ai_voice.flac"></audio>',
            '<h2>Transcript review</h2><p>Notes flag uncertain words; English subtitles clarify meaning but cannot prove the original Lithuanian wording. Reference conditioning may still reproduce background characteristics.</p><table>']
    for item in entries:
        page.append(f'<tr><th>{args.start + item["start_sec"]:.2f}s</th><td lang="lt">{html.escape(item["lt"])}</td><td>{html.escape(item["review_note"])}</td></tr>')
    page.append('</table>')
    if out != baseline and not args.transcript:
        previous = "../omnivoice_149_1550_1740"
        page.insert(3, f'<h2>Previous version</h2><video controls src="{previous}/Dragon.Ball.Z.149.1550-1740.LT-OmniVoice.mp4"></video><h2>New version</h2><p>Three shared reference voices, natural generation timing, {args.candidates} candidates per line. Automatic selection minimizes speed-up; it does not judge which performance sounds best. The Japanese mix settings are unchanged.</p>')
        page.append('<h2>Voice alone: previous / new</h2>')
        page.append(f'<p>Previous</p><audio controls src="{previous}/ai_voice.flac"></audio><p>New</p><audio controls src="ai_voice.flac"></audio>')
        page.append('<h2>Individual candidates</h2><p>These are unadjusted generations. Compare the same sentence for distance, metallic sound, stress and delivery.</p>')
        for item, selection in zip(entries, selections):
            page.append(f'<h3>{args.start + item["start_sec"]:.2f}s — {html.escape(item["lt"])}</h3>')
            for candidate in range(args.candidates):
                selected = ' — selected for render' if candidate + 1 == selection["candidate"] else ''
                page.append(f'<p>Candidate {candidate + 1}{selected}</p><audio controls preload="none" src="generated/candidate_{item["idx"]:03d}_{candidate + 1}.wav"></audio>')
    (out / "index.html").write_text('\n'.join(page), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps({"tts": "k2-fsa/OmniVoice", "num_step": args.steps,
        "shared_references": args.shared_references, "natural_timing": args.natural_timing,
        "candidates": args.candidates, "selections": selections,
        "seed": "42 + line ID", "original_lithuanian_audio_in_mix": False, "rvc": False,
        "mix_inputs": [str(jp), str(voice)], "source_window": [args.start, args.start + args.duration], "reused_preview": args.reuse_preview,
        "transcript_status": "ASR comparison with spelling/context corrections; flagged words need listener verification"}, indent=2))
    print(f"Verified {len(entries)} generated lines and {args.duration}-second video. Open {out / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
