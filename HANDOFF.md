# Dubbing handoff — 2026-10-13

## Where we stopped

The user finished for today and wants to continue another day without explaining the project again. No generation or render jobs remain running.

The full episode 149 render is complete. The user said: “this is impressive, I really like this.” Treat it as the accepted baseline. The remaining issue is that some lines sound distant, thinner, or less rich, then the voice returns to normal. Do not replace the whole performance or start another full render immediately.

## User's goal and constraints

- Keep the original Lithuanian dub's wording.
- Generate fresh Lithuanian speech with OmniVoice and actor reference conditioning.
- The original Lithuanian dub is recorded over Spanish dialogue. Use it for transcription and reference conditioning only; never mix its waveform into the finished dub.
- Mix AI Lithuanian speech over the Japanese soundtrack, ducking Japanese audio during speech. The Japanese track still contains Japanese dialogue; it is not a dialogue-free music/effects stem.
- No RVC in the accepted approach.
- English subtitles can help resolve unclear passages, but do not replace the original wording with a new translation. Flag uncertain reconstructions.
- Preserve the accepted preview and full render. Experiment in separate output directories.
- The user likes playback pages with video, dry AI voice, and transcript review.

## Accepted artifacts

Full episode directory: `output/omnivoice_149_full_original/`

- `Dragon.Ball.Z.149.LT-OmniVoice.mp4` — accepted full episode, 24:41.6.
- `index.html` — playback and transcript review.
- `ai_voice.flac` — generated voice alone.
- `mixed.flac` — final AI voice + Japanese audio.
- `japanese.flac` — extracted Japanese soundtrack.
- `transcript.json`, `transcript.vtt` — 97 dialogue entries.
- `generated/line_001.wav` through `line_097.wav` — selected AI takes.
- `references/` — local reference clips.
- `settings.json` — generation/mix provenance and targeted repairs.
- `generated_speech_check.json` — ASR diagnostics; not proof of pronunciation or acting quality.
- `repairs.json`, `short_reply_repairs.json`, `verification.json`.

Original accepted preview: `output/omnivoice_149_1550_1740/`, covering 15:50–17:40. Its 25 generated takes were copied unchanged into the full episode. They map through `preview_idx` in the full transcript. The full mix has global normalization and timeline fitting, so copied takes do not imply identical final mixed samples.

Rejected experiment: `output/omnivoice_149_1550_1740_consistent/`. It used three shared references, natural timing, and three candidates per line. The user preferred the first preview. Do not assume one shared reference for the whole episode improves it. Automatic candidate selection in that experiment minimized timing acceleration, not audible artifacts or acting quality.

## Next goal

Make occasional distant/thin lines more consistent while preserving the delivery the user already likes.

The last reply proposed targeted repairs. These causes are hypotheses, not verified diagnoses:

1. Local actor references vary in muffling, room sound, background Spanish voices, and recording quality. OmniVoice may reproduce those characteristics.
2. Short references and generation variability may produce weaker or incorrect takes.
3. Japanese background audio can mask a good AI take and make it feel farther away.
4. Forced duration or subsequent tempo fitting may contribute to artifacts.

At the next session, first ask for a few episode timestamps if the user has them. Compare the selected raw generated take, assembled dry AI track, and final mix at those moments. If the dry voice is bad, regenerate only that line using a nearby clean, expressive actor reference. If only the mix sounds distant, adjust masking/loudness locally. Compare before/after in a separate review page. Gentle level/tonal matching may help, but cannot fix incorrect speech or severely robotic generation. Do not train a model or redesign the pipeline without evidence that it is needed.

No specific bad timestamps have been provided. The short name “Selas?” at about 21:51 is already flagged for listening review because ASR remained uncertain.

## Implementation and reproduction

Runner: `tests/omnivoice_scene_test.py`. It now accepts a full transcript, window start/duration, output directory, and reuse of the accepted preview. Default behavior remains the original scene test. It validates timing/text, resumes existing valid generated clips, generates local references, assembles speech, mixes Japanese audio, renders MP4, and builds the review page.

Reviewed full-episode input: `data/translations/ep149_original_lt_reviewed.json`. Derived from the original Lithuanian ASR, with spelling/name corrections, uncertain wording flagged, a suspected separated-audio repetition removed, and accepted preview lines substituted. It has not been completely verified by listening to every original phrase.

Base full-episode command:

```bash
tools/Applio/.venv/bin/python tests/omnivoice_scene_test.py \
  --transcript data/translations/ep149_original_lt_reviewed.json \
  --start 0 --duration 1481.605 --reuse-preview \
  --out-dir output/omnivoice_149_full_original
```

This command documents the base render; do not run it over the accepted output. A fresh directory recreates the base approach, but does not automatically reproduce the five subsequent targeted repairs. The accepted output's `settings.json` records those repairs. Resume uses existing WAVs and does not prove they match changed options, so use a fresh directory for changed settings.

Accepted base generation: `k2-fsa/OmniVoice`, CUDA, float16, Lithuanian language, 32 steps, one take per line, seed `42 + line ID`, requested duration matching Lithuanian speech timing. Short references borrow nearby complete phrases where feasible, with a 9.5-second ceiling. Reference processing: highpass 70 Hz, FFmpeg `afftdn=nr=6:nf=-45`, 24 kHz mono, peak limited to 0.85. There is no guaranteed exact transfer of the actor's intonation.

Timeline helper: `src/mix_and_remux.py::assemble_vocals_timeline`, `fit_timing=True`. Keeps starts and accelerates speech only when needed to avoid the next line. Existing runnable check: `tools/Applio/.venv/bin/python tests/test_timeline.py` passed.

Mix: only Japanese audio and generated AI speech; sidechain threshold 0.03, ratio 4, attack 20 ms, release 350 ms; voice volume 1.3; amix then volume 1.25; peak limited to 0.95. MP4: H.264 CRF 18, AAC 256 kbps.

Five new takes required targeted repairs: IDs 14, 23, 33, 84, 95. The first repair shortened problematic durations; the second used better references for short replies. Final durations: 14 = 1.8 s, 23 = 0.7 s, 33 = 4.0 s, 84 = 0.9 s, 95 = 0.9 s. Exact selected seeds and alternate references are in `settings.json::targeted_repairs`. “Selas?” remained uncertain. Temporary repair/remix scripts were in `/tmp`; the durable provenance is in the output JSON files, not those temporary scripts.

## Source files and environment

- Workspace: `/home/jurgis/git/me/dubvertejas`.
- Source: `media/Dragon.Ball.Z.149.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv`.
- Source streams: Lithuanian audio 0, video 1, Japanese audio 2, English SRT 8.
- Separated reference stem: `temp/ep149_original_jp/separated/htdemucs/original_lt/vocals.wav`. It still contains some foreign voices; never use it as final dubbed audio.
- Original ASR evidence: `temp/ep149_reference_ai/transcript.json` (separated audio), `raw_transcript.json` (original audio).
- English context: `data/translations/ep149_translated_clean.json`; its Lithuanian translations are not the original dub wording.
- Python: `tools/Applio/.venv/bin/python`. Plain `python` is unavailable.
- RTX 4060, 8 GB; CUDA works. OmniVoice 0.2.1, Torch 2.11.0+cu130, transformers 5.13.1.
- Cached ASR: `WhisperModel('large-v3', device='cpu', compute_type='int8', cpu_threads=8, local_files_only=True)`.
- FFmpeg available. No sub-agents/delegation authorized.
- Most project files are untracked; do not revert or clean user work. `media/`, `temp/`, and `output/` are ignored by Git, so preserve their local files.
- README describes an older RVC direction and makes overly strong pronunciation claims. This handoff records the currently accepted OmniVoice approach.

## Verification completed

97 valid, finite, non-silent selected WAVs; all 25 reused preview WAVs byte-identical; final video duration 1481.605 seconds; one audio stream; clean FFmpeg audio decode; finite full tracks and safe mixed peak. Timeline checks and Python compilation passed. Automatic recognition detected Lithuanian with probability about 0.9995 on the 72 new takes, but it has spelling/name errors and coarse segment boundaries. Five suspect takes were checked individually and repaired; do not claim all artifacts are eliminated.

The Japanese source audio ends at about 1477.05 seconds, shorter than the video; the final mixed track is padded to the full duration. This is reflected in `verification.json`.
