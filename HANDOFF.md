# Dubbing handoff — 2026-10-14

## Manual original-Japanese choice — 2026-10-14

- Added Original Japanese to every review take selector, alongside Original Lithuanian take and regenerated alternatives. Preview uses native audio media fragments on the original Japanese WAV at the cue's start/end. Choose Use this take and rebuild to retain Japanese for that cue.
- Review choices accept `japanese`; rebuilt transcripts keep the line/text/AI clip with `keep_japanese=true`, so the rebuilt page can restore Lithuanian later. Generation/checking omit those flagged rows; rendering protects their original Japanese windows from AI and ducking and omits Lithuanian captions there. Review rows remain visible. All-Japanese and mixed choices work, including restoring an AI line from a Japanese baseline.
- Tiny real-render regression verifies all-Japanese background, silent AI, preserved source/clips, absent LT captions, visible editor rows and restoring Lithuanian in a later rebuild. Existing fallback regression passed. Native Chromium confirmed all 236 selectors and that original Japanese preview starts at 129.4s and stops at 130.78s for line33. Restarted the idle local UI with updated backend (PID 593154). No real episode was rebuilt or selections changed; reload the existing page.

## Interactive line editing and alternative takes — 2026-10-14

- User requested editing/retrying individual voices on `http://127.0.0.1:8765/output/gemini/068/8144477b3a5a/index.html`. Added `dub_review.py` and dependency-free `review_editor.js`, served/injected by `gemini_ui.py` into existing completed review pages without changing their HTML files. Every dubbed line has a text editor, Regenerate this line, alternate-take preview/selector and Use this take. Text edits do not enter the chosen version until regenerated and explicitly selected. Each retry uses the same Japanese reference and source generation steps with a new random seed.
- Takes live under `<source>/review/takes/<uuid>/` with immutable clips/metadata. Working choices live in `review/selection.json`; choosing Original clears that line's choice. Rebuild video freezes choices and creates sibling `edit-<uuid>/`, copying unchanged voices byte-for-byte and remuxing a new video. Original transcript, clips and render remain intact. Rebuild history links are retained under `review/renders.json`; the existing video above the editor stays its original version until opening the rebuilt video. No ASR/generation pass for unchanged lines or rebuilding.
- Added review GET/POST routes to the existing local Host/Origin-protected server. Validates output/line/take/text/seed paths and associations. A shared single-job lock prevents concurrent GPU jobs; logs/state are polled by the review UI. Regeneration loads OmniVoice per edit; no persistent GPU worker or new dependencies. Generator supports per-row `generation_seed` while preserving all existing default fingerprints.
- Restarted the idle/completed server (old PID 401770) with the updated UI, now detached with log `output/gemini_ui_logs/server.log`. The user's URL works immediately after reload. Created one native offline CUDA test take for episode068 line33 with exactly the original wording; stored at `review/takes/afb434c2d9734cd58230f0c7dff9013c/`. It is available for listening but unselected. No full real episode rebuild started.
- `tests/test_review_editor.py` verifies changed text, take association/input validation, frozen selections, a real tiny video rebuild, unchanged source/clips, server HTML injection, local origin rules, selection APIs and GPU job exclusion. Existing fast/fallback/import/workflow tests and compilation passed. Native OmniVoice retry ran successfully. Live headless Chromium checked all 236 editors, alternate previews, edited-text safeguards and no JavaScript errors. Original source index/transcript/settings/generation metadata and all 236 original generated WAVs were checksum-verified unchanged after the smoke test.

## Fast dubbing variant — 2026-10-14

- User finished episode 086 and authorized speed experiments. Added `dub_gemini.py --fast`: local cached Whisper base Japanese references, 24 OmniVoice steps, one line at a time, generated-speech checking skipped. Optional `--steps 16|24|32`, `--reference-model base|large-v3`, `--batch-size 1|2`, `--skip-speech-check` propagate through preparation and runner. Defaults retain large-v3/32 steps/checking. UI has an unchecked Fast variant option; the user's existing server must restart to load it.
- Output hashes include speed settings, so experiments never overwrite accepted renders. Source-identical Japanese extraction/separation is copied using reflinks when available, without copying voice generation or ASR from incompatible settings. Generation fingerprints include nondefault steps/batch size. A fully cached generation returns before loading OmniVoice. Preferred Krillin take 2 copies remain byte-identical. Batch-of-two uses separate prompts and records batch seeds/IDs/time; GPU OOM releases the exception scope before retrying single lines. Completed output settings reject incompatible regeneration/rendering. Skipped speech checking is explicit in review/settings/verification.
- Actual offline RTX 4060 four-line generation benchmark (warmed, excludes loading/ASR/render): 32 steps/single 3.59s; 24/single 2.71s; 16/single 1.84s; 24/batch2 3.18s. Batching was slower than singles here and is optional. Japanese ASR on the same references: large-v3 1.78s; base 0.34s, but base introduced more text errors. No quality-equivalence claim; listen to samples. CPU reference recognition overlapping GPU generation was deferred: it requires pipeline restructuring, and the simpler GPU path is already fast on the short benchmark. No threading rewrite was made.
- Listening comparison includes copied accepted samples, fresh 32/24/16-step large-reference samples, batch2 samples, and actual 24-step/base-reference samples at `output/gemini/086/fast-preview-20261014/index.html`, served by the existing UI at `http://127.0.0.1:8765/output/gemini/086/fast-preview-20261014/index.html`. Benchmark JSON files accompany it. Four-line fast generation and immediate cache resume ran successfully using the updated runner. No full fast episode render was launched.
- Fast episode output `output/gemini/086/7a583848b466/` has validated imported wording, manifest and reused Japanese separation ready. Full command: `unshare -Urn tools/Applio/.venv/bin/python dub_gemini.py 86 --fast`. Use `--fast --reference-model large-v3` if avoiding weaker reference ASR is preferred; that creates its own output version.
- Tests passed: fast batching/OOM/cache/provenance/CLI forwarding/audio reuse, preferred take copying, Japanese fallback real mixing with skipped checking, Gemini workflow, translation import, honorific normalization and compilation. All 125 accepted episode086 generated WAVs still match their stored SHA256; accepted settings remain 32 steps. README updated.

## Automatic Japanese reference fallback — 2026-10-14

- Episode 086 Gemini run stopped at subtitle 59 after saving 24 Japanese references. Fixed `dub_local.py` to checkpoint unusable references in `skipped_references.json`, omit AI for those windows, and continue for all input types. Resume excludes skipped IDs even if interrupted between checkpoint writes. Imported Lithuanian wording remains unchanged.
- Added conservative ASR quality checks (empty text, compression ratio >2.4, no-speech probability >0.6, average log probability <-1). Gemini reference retries use separated vocals only; no retry using music/effects-containing original audio. These heuristics do not classify all music/crowds or guarantee actor isolation. Previously cached references are reused, not retroactively checked.
- Renderer protects skipped windows from dialogue ducking and AI spillover; all-skipped input renders Japanese without loading generation/check models. The existing overall soundtrack gain remains in effect.
- Gemini output hashes include the reference policy; interrupted legacy preparation resumes its saved files, while completed legacy renders stay preserved. Current episode 086 resumes `output/gemini/086/0fe1b464f21c/` with `unshare -Urn tools/Applio/.venv/bin/python dub_gemini.py 86`, or Start in the UI. No real episode render was launched during this fix.
- `tests/test_reference_fallback.py` checks rejection, preparation continuation, resume/crash recovery, unchanged wording, preserved completed versions, actual Japanese-only rendering and adjacent fallback mixing. Existing workflow/import/honorific checks and Python compilation also passed.

## Aligned original-Lithuanian variant and GPU recognition — 2026-10-14

- User's original-text run separated Japanese audio successfully, but reference ASR stopped at original transcript line 43. Lithuanian phrase timings differed from Japanese speech; very short cropped references also produced repetitive/hallucinated Japanese ASR. User explicitly requested moving Lithuanian dialogue to the corresponding Japanese timing, then clarified that uncertain/missing matches should retain Japanese.
- Added `--asr-device cpu|cuda` to `dub_local.py` and `tests/japanese_cast_episode.py`; default remains CPU. CUDA uses cached Whisper large-v3/int8_float16 for Japanese references and generated-speech checking. Shared `enable_cuda_asr()` provides cached CUDA 12/cuDNN library paths; no downloads/cloud. CUDA preparation replaces its process with the generation runner so CTranslate2 releases GPU resources before OmniVoice loads; speech checking clears Torch's unused CUDA cache before loading Whisper.
- Recorded-transcript references now use whole corresponding Japanese subtitle cues, reuse the same cue reference for multiple phrases, disable cross-segment conditioning, reject repetitive recognition, retry missed short speech without VAD, then retry the original Japanese cue if separation removed speech. No recorded Lithuanian audio enters references or mix. If a recorded-transcript reference remains unusable, omit its AI line and checkpoint it in `skipped_references.json`, leaving Japanese in that window. Full cues still do not guarantee correct actor identity or ASR text.
- `align_lt_dub.py` performs ordered lexical matching between original Lithuanian ASR and existing Lithuanian subtitle meanings, using stdlib only. Gemini text is a matching hint only: no Gemini wording is substituted into spoken lines. Matching respects order, searches within 45 seconds, permits spans of up to three Japanese cues, splits shared windows proportionally, and retains initial times. Heuristic scores are not probabilities/semantic proof; unclear synonyms or poor ASR are conservatively skipped. Earlier Qwen-based experiments in `output/068_original_lt_aligned/` and `output/068_original_lt_japanese_timing/` failed validation or ran too slowly; preserved but unused. No alignment model/job remains running.
- Final timing data: `output/068_original_lt_matched_timing/transcript.json`, 91 selected phrases; `alignment.json` contains every original phrase's mapping/score; `skipped_phrases.json` preserves 142 uncertain phrases to remain Japanese. Original phrase 43 matched Japanese subtitle 78 and moved from 378.73–381.09 to 387.54–389.87. Phrase 42 matched 77 but was conservatively skipped due to its lexical score. All selected original Lithuanian strings remain unchanged; ASR spelling errors are not corrected.
- New prepared output: `output/omnivoice_068_japanese_original_lt_aligned/`. All 91 references prepared successfully with GPU and external networking disabled; line 43 reference is `早いうちに連れてこの星から出ていけ`. Existing Japanese WAV/separation tracks were copied via reflink from the failed variant to avoid repeated separation, leaving its files intact. Review page and transcript are ready. No new speech generation/render started.
- Continue with episode 68 `dub_local.py --out-dir output/omnivoice_068_japanese_original_lt_aligned --transcript-file output/068_original_lt_matched_timing/transcript.json --asr-device cuda`. Existing Gemini, NLLB, accepted 149 and failed original-timing variant are preserved. The renderer retains original Japanese outside the selected dubbed dialogue windows.
- `tests/test_dub_alignment.py`, translation-import and honorific regressions, and Python compilation passed. Actual isolated CUDA speech-check smoke on a copied accepted Gemini clip passed (similarity 1.00, 6.1 seconds including model loading); accepted outputs were not modified. Runner now allows repeated source cue IDs for recorded transcripts, since multiple original speech segments can match one source subtitle. README updated.

## Episode 68 recorded Lithuanian wording variant — 2026-10-14

- User liked the completed Gemini variant and requested a separate variant using the existing Lithuanian audio track's actual wording with Japanese voice references. Treat the completed Gemini render as accepted; preserve it along with prior outputs.
- Added `transcribe_lt_dub.py`: extracts stream 0 (`lit`, professional Lithuanian), transcribes whole dialogue blocks with cached Whisper large-v3 on CUDA/int8_float16, saves raw block ASR/confidence checkpoints, then creates a timed Lithuanian transcript and source-audio listening page. No Qwen/NLLB/Gemini text is substituted. English Basic Subtitles identify dialogue windows/context only. Lithuanian speech outside those windows may be missed; there is no speaker diarization or guarantee of background-language rejection.
- GPU inference succeeded with external networking disabled. CTranslate2 needs CUDA 12, while this workspace's Torch uses CUDA 13; script reexecs with cached `/usr/local/lib/ollama/cuda_v12` and venv `nvidia/cudnn/lib` in `LD_LIBRARY_PATH`. No packages/models downloaded.
- Completed `output/068_original_lt_transcription/transcript.json`: 233 timed phrases. `index.html` has full original Lithuanian audio plus clickable listening times, recognized Lithuanian text, English context and review notes. `block_001.json` through `block_016.json` retain raw ASR results. Block 16 returned no Lithuanian phrases; no replacement preview wording was invented. Original wording is an ASR draft: names and endings have obvious recognition errors; no claim of a listening-verified transcript. 94 phrases overlap multiple Japanese cues or lack a direct single-cue alignment and are flagged.
- Added `dub_local.py --transcript-file` for a JSON transcript with its own timing; validates text, unique IDs, finite/nonoverlapping timing and optional context, fingerprints the source, snapshots it as `source_transcript.json`, and bypasses translation models. Existing imported lt edits survive continuation. Missing lt fields stop with an error rather than falling back to translation. Mutually exclusive with `--translation-file`.
- Prepared `output/omnivoice_068_japanese_original_lt/transcript.json` and `translation_review.html` using these 233 phrases (`--translate-only`); no Japanese reference preparation, voice generation or new render started. To render, run the episode 68 command with `--out-dir output/omnivoice_068_japanese_original_lt --transcript-file output/068_original_lt_transcription/transcript.json` and without `--translate-only`. If reviewing wording now, edit this prepared output's lt fields to preserve its import fingerprint; changing the source file after import requires a fresh output directory.
- Expanded `tests/test_translation_import.py` passed (original wording/timing, repeated IDs, overlaps, missing text, out-of-range/NaN timing). Honorific regression and Python compilation passed. README documents the transcript workflow and limitations. Recorded Lithuanian audio is solely for transcription/listening, never the mix or Japanese voice references.

## Gemini translation import — 2026-10-14

- User supplied `media/gemini-code-1791969941448.txt` and authorized using its Lithuanian translation. Added `--translation-file` to `dub_local.py`: imports SRT text by subtitle ID, validates missing/duplicate/unknown IDs, bypasses model translation, fingerprints the imported file and preserves manual lt edits on resume.
- Prepared `output/omnivoice_068_japanese_gemini/transcript.json` and `translation_review.html` with all 242 dialogue cues. Gemini supplied 248 cues; on-screen cues remain excluded by original source filtering. Original video subtitle timings are retained, including IDs 114 and 120 whose Gemini timestamps differ. Imported wording matches supplied text after subtitle markup removal; no grammar/name edits made.
- `tests/test_translation_import.py` passed; all 242 imported lines and original timings verified. No audio generation started. Continue with the existing episode 68 command using `--out-dir output/omnivoice_068_japanese_gemini --translation-file media/gemini-code-1791969941448.txt` and without `--translate-only`. Existing Qwen/NLLB and accepted outputs are preserved.

## Translation suffix recovery — 2026-10-14

- Episode 68 Qwen translation stopped at conversation 7 because line 146 retained `Frizas-sama` after both editing attempts. Conversations 1–6 remain checkpointed.
- `dub_local.py` now removes honorific suffixes only from Lithuanian forms present in the supplied glossary, retaining the raw model response in scene checkpoints. Applies to fresh final edits and reused scene results. Unknown aliases such as `Son-kun` still require contextual model editing; retry feedback includes the offending lines.
- `tests/test_translation_honorifics.py` passed, covering the reported phrase, inflected names, unresolved aliases, unchanged text and raw input preservation. No translation or audio job started; rerun the existing episode 68 Qwen `--translate-only` command to resume. Profile and glossary hashes are unchanged.

## Where we stopped

The latest result is the full Japanese-cast experiment in `output/omnivoice_149_japanese_cast/`. The user liked the Krillin test and preferred take 2, then authorized this full episode. It is complete and awaits listening review. No generation or render jobs remain running. See the latest section below for details.

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

## Earlier repair goal — Lithuanian actor baseline

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

## Japanese Krillin voice experiment — 2026-10-14

The user explicitly requested a separate test of Japanese Krillin speaking Lithuanian, with new translations from English subtitles. This authorizes newly translated wording for this experiment; it does not change the accepted original-wording baseline.

- Preview: `output/krillin_japanese_lt_test/index.html`.
- Three Japanese Krillin moments: 15:54.50–15:57.80 (worried reply), 16:46.50–16:53.55 (urgent phone request), 17:15.20–17:17.35 (quiet reaction).
- Two OmniVoice takes per line, 32 steps, scene-specific Japanese references, natural generation timing. Dry speech remains available; video versions speed up only where necessary to fit the scene.
- Japanese 15:50–17:30 soundtrack separated with cached htdemucs. References come from its vocals stem. Test mixes contain fresh AI Lithuanian speech and its no-vocals music/effects stem, which can contain separation artifacts/residual dialogue. No recorded Lithuanian/Spanish audio used.
- Japanese reference transcriptions use cached Whisper large-v3. The short third reference returned `赤いか`; provisionally corrected to `破壊か。` using the subtitle “Destroy, huh?”. This correction is unverified by listening and exposed in the preview.
- Runner: `tests/krillin_japanese_audition.py`. Requires the experiment's existing transcript/reference/separation files; it does not extract or transcribe references itself. Assertions validate speech, mix samples, video durations and audio stream count.
- Settings and per-take seeds/durations recorded in `settings.json`; recognition diagnostics in `speech_check.json`. Neither ASR nor structural checks establish voice likeness or expression transfer. Both takes are exposed for user listening; no claim of audible quality yet.
- Accepted full episode and previous previews were not modified. Await user judgement of this experiment before further generation.
- ASR recovered approximately the intended Lithuanian words in five takes. Urgent line take 2 was identified as Bulgarian and transcribed in Cyrillic; flagged on the page for pronunciation review. Start with urgent take 1. Short-line language probabilities are low, so these are diagnostic signals rather than confirmed pronunciation findings.

## Full Japanese-cast episode — 2026-10-14

The user called the Krillin experiment “very promising”, requested the whole episode with every speaking character conditioned on the Japanese source, and clarified that take 2 was always better. This explicitly authorizes a fresh English-subtitle-to-Lithuanian translation for this separate full-episode experiment.

- Output directory: `output/omnivoice_149_japanese_cast/`.
- Full video: `Dragon.Ball.Z.149.LT-Japanese-Voices.mp4`, 1481.605 seconds.
- Review page: `index.html`, with full video, Lithuanian captions, dry full AI track, Japanese source audio, clickable dialogue timestamps, individual AI lines and Japanese references.
- 113 dialogue/title subtitle entries grouped into 77 same-speaker passages. Opening/closing songs and nonverbal sounds remain Japanese. Spoken episode title included; on-screen song lyrics/signs are not synthesized as dialogue.
- 15 speaking roles: narrator, Android 17, Android 18, Piccolo, Cell, Gohan, Goku, Krillin, Tien, Yamcha, Dr Brief, Bulma, Yajirobe, Master Roshi, Chi-Chi. Cast mapping uses frames, Japanese phrasing and scene context, not automatic speaker diarization. Simultaneous reactions and preview speaker assignments remain listening-review items.
- References are extracted from full Japanese htdemucs vocals. Short replies borrow references only from the same speaker. Japanese ASR uses cached Whisper large-v3; clear substitutions were corrected using scene/subtitle context and raw evidence retained. Reference text is not fully listening-verified.
- Same OmniVoice cross-language method as the promising test: Lithuanian, 32 steps, natural timing, seed `1042 + first subtitle ID` (second-take pattern). Timing acceleration only when necessary to fit scene windows. Preferred Krillin take 2 WAVs copied byte-identically for subtitle IDs 97, 112+113 and 117; original test wording retained there.
- Input and provenance: `transcript.json`, `reference_transcriptions.json`, `generation.json`, `settings.json`, `placements.json`, `verification.json`, and `speech_check.json`. Preparation script retained as `prepare_transcript.py` within the output directory. Do not rerun preparation blindly over reviewed references/transcripts.
- Durable generation/check/render runner: `tests/japanese_cast_episode.py --stage generate|check|render`, using `tools/Applio/.venv/bin/python`. Generation checkpoints finished WAVs with fingerprints. `--repair ID` retains the prior WAV as `generated/previous_ID.wav`.
- Mix uses newly generated Lithuanian speech only. Original Japanese soundtrack is retained outside dialogue windows; no-vocals Japanese stem replaces it during dubbed dialogue, with smoothed transitions. Background gain 0.65, voice 1.3, limiter 0.95. Separation can remove sound effects or leave Japanese residue. No Lithuanian/Spanish recording used.
- Initial full render passed duration, one-audio-stream, decode, finite/non-silent audio and review-asset checks. Three preferred preview copies were byte-identical. Two brief replies required up to roughly 1.82x fitting; most lines fit naturally or with modest acceleration.
- One short Tien “S-Selas?” reaction (ID 75) was missed by ASR. Its written stutter was removed and a new alternate generated (seed 2117), with the initial take retained. Both recognition and acting still require listening judgement.
- Previous accepted Lithuanian-actor full render and all Krillin preview files are preserved. This new full episode awaits user listening judgement; do not claim exact actor identity/expression transfer or uniformly correct pronunciation.

- Final refresh completed with the repaired ID 75 (recognition recovered “Selas!”). All 77 recognition checks match the final selected WAV hashes; minimum normalized text similarity about 0.67. Final render passed duration, audio decode, finite audio, asset and preferred-copy checks. ASR flags are exposed for listening review; they do not establish pronunciation/acting quality. The final video copies the original H.264 video stream. No jobs remain running.

## Offline command requested — 2026-10-14

The user praised the Japanese-cast full episode and requested a command for episode 68 using only their computer. They chose “automatic for now”. Episode 149 Japanese-cast output is now an accepted result; preserve it.

- Added `dub_local.py`: automatically extracts Japanese audio and English Basic Subtitles, removes paired song lyrics/on-screen top-position cues, translates with cached NLLB 600M, separates with cached local htdemucs weights, transcribes scene references using local Japanese Whisper, then generates/checks/renders through `tests/japanese_cast_episode.py`.
- NLLB's cache has no main ref; use cached revision `f8d333a098d19b4fd9a8b18f94170487ad3f821d`. No download needed. Demucs explicitly uses the local checkpoint repository and signature `955717e8`, so no remote repository lookup.
- Main command from project root: `unshare -Urn tools/Applio/.venv/bin/python dub_local.py --video media/Dragon.Ball.Z.068.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv --out-dir output/omnivoice_068_japanese_auto`.
- Network isolation with `unshare -Urn` works on this computer and was used for the end-to-end test. Scripts also enforce Hugging Face/Transformers offline mode. Full episode 68 render was not started; the user requested a runnable command.
- `--prepare-only` prepares editable `transcript.json`; the same command without it continues generation. Repeating the same command reuses preparation, reference transcriptions and finished generated WAVs. Use a fresh output directory for a different/changed source.
- This is an automatic first draft, not the manually reviewed actor/translation mapping used for episode 149. Each subtitle gets its own Japanese scene reference; short replies do not borrow from automatically identified actors. References containing multiple speakers and local translation quality need listening/text review. Songs and on-screen titles remain Japanese. No recorded Lithuanian/Spanish audio enters the output.
- Generalized `tests/japanese_cast_episode.py` with `--video`, `--out-dir`, variable duration and `--stage all`. Existing 149 defaults remain. New outputs derive filenames from the source; review pages identify automatic preparation limits. Accepted renders were not regenerated.
- `tests/test_local_dub.py` passed inside a network-disabled namespace: song filtering/shared timing assertions and a 3.4-second episode 68 clip through separation, local translation, Japanese ASR, OmniVoice generation, recognition checks, audio mix, video render and decode validation. All temporary test outputs were removed. Episode 68's 242 automatically retained dialogue cues have valid non-overlapping timing.
- README now contains local commands above the older RVC documentation. No generation/render jobs remain running.

## Contextual local translation and Lithuanian reference — 2026-10-14

The user finished the episode 68 automatic render, found NLLB translations too literal and context-poor, and requested local scene-based Qwen translation plus a Lithuanian DBZ reference. Preserve the finished episode 68 output as well as all accepted 149 outputs. New translation defaults are intentionally incompatible with resuming the old NLLB output unless `--translator nllb` is specified.

- `dub_local.py` now defaults to cached `qwen3:8b` through a private local Ollama server. Uses dialogue blocks of up to 24 cues, splits on gaps over 12 seconds, includes six previous/following cues and previous Lithuanian translations, full glossary, focused matching glossary entries and episode story notes. Timing is an approximate conversation boundary, not visual scene/speaker detection.
- Each block has a translation pass and a Lithuanian editing pass. Ollama JSON schema requires exactly the target subtitle ID keys; runtime validation rejects omitted/extra IDs, duplicate JSON keys, empty/oversized/control-character text and retained Japanese honorifics. Scene checkpoints include input/model digests, draft and final results. Translation progress is atomically checkpointed after each block; reviewed `lt` fields survive continuation.
- No cloud calls or model downloads: cached model lookup only; private localhost server ignores proxy settings and sets `OLLAMA_NO_CLOUD=1`. Inside `unshare -Urn`, the script enables loopback only for the private server, with external networking still unavailable. Private server/runner is stopped and Qwen unloaded before Demucs/OmniVoice. The existing host Ollama service is left alone.
- New editable reference: `data/context/dragon_ball_lt.md`. Names/aliases and inflections, locations, terminology, character tone and useful construction examples. Earlier project names are retained; additional names/terms are explicitly starter suggestions, not asserted official Lithuanian canon. User can edit this file or supply `--glossary`.
- Episode notes: `data/context/ep068_lt.md`, automatically selected by `.068.` filename, or use `--episode-context`. Notes distinguish guesses from confirmed facts, explain Frizo wish/Grand Elder stakes and Bulma's Son-kun alias, and include a few subtitle-specific speaker/context hints. These hints inform translation only; audio speaker diarization is unchanged.
- `--translate-only` extracts English subtitles, translates and creates `translation_review.html`, `transcript.json`, glossary/episode-note snapshots and scene checkpoints, without audio extraction/separation/generation. Remove that flag to continue the same output after reviewing/editing the lt fields. `--prepare-only` still includes reference preparation. Translator/model/reference hashes are recorded in `preparation.json`; changing them requires a fresh output directory.
- Suggested command: `unshare -Urn tools/Applio/.venv/bin/python dub_local.py --video media/Dragon.Ball.Z.068.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv --out-dir output/omnivoice_068_japanese_qwen --translate-only`. Full new episode translation/render has not been started during this implementation turn.
- Actual 20-line offline comparison: `output/068_qwen_scene_translation/translation_review.html`, with previous NLLB and new Qwen outputs for IDs 123–134 and 176–183. Improved examples: “I've had it with Dad” now “Man jau gana tėvo.”; Son-kun aliases become Gokas; Dragon Balls/Namek/Shenron terminology is more consistent. Qwen 8B still makes real Lithuanian errors: e.g. “rūpinuosi Gokas” has a wrong case, and some relative clauses are awkward or imprecise. Do not claim polished/native translation or guaranteed meaning preservation. Comparison output is unedited model output, exposed for user judgement.
- `tests/test_local_dub.py` passed with external networking disabled: cue/song filtering, shared timing, missing/repeated/invalid IDs, duplicate JSON key rejection, focused glossary lookup, actual local Qwen translation/editing, translation-only without audio work, manual lt edit surviving continuation, local Demucs/Japanese ASR/OmniVoice and successful audio/video decode. Temporary smoke outputs were removed. A separate guard check confirmed the finished NLLB preparation manifest remains unchanged when the new defaults refuse to overwrite it.
- README documents the new command, context files, review-first option, offline Ollama setup and legacy NLLB continuation. No new dependencies added and no generation/render/translation jobs remain running.
