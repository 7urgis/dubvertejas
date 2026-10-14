"""Run with tools/Applio/.venv/bin/python tests/test_timeline.py."""
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mix_and_remux import assemble_vocals_timeline

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    sr = 8000
    sf.write(root / "line_001.wav", 0.5 * np.sin(2 * np.pi * 300 * np.arange(2 * sr) / sr), sr)
    sf.write(root / "line_002.wav", np.full(sr // 4, 0.25), sr)
    subtitles = root / "lines.json"
    subtitles.write_text(json.dumps([
        {"idx": 1, "start_sec": 0.5, "end_sec": 1.5, "lt": "Pirma."},
        {"idx": 2, "start_sec": 1.5, "end_sec": 2, "lt": "Antra."},
    ]))
    output = root / "timeline.flac"
    assemble_vocals_timeline(str(subtitles), str(root), str(output), 2.5, sr, fit_timing=True)
    audio, actual_sr = sf.read(output)
    assert actual_sr == sr and len(audio) == int(2.5 * sr)
    assert np.max(np.abs(audio[:sr // 2])) == 0
    assert np.max(np.abs(audio[sr // 2:sr])) > 0.1
    assert np.all(audio[int(1.5 * sr):int(1.75 * sr)] > 0.1), "Second line shifted or overlapped"
    assert np.max(np.abs(audio[int(1.75 * sr):])) == 0
    subtitles.write_text(json.dumps([
        {"idx": 1, "start_sec": 0.5, "end_sec": 2, "lt": "Pirma."},
        {"idx": 2, "start_sec": 0.5, "end_sec": 2, "lt": "Antra."},
    ]))
    assemble_vocals_timeline(str(subtitles), str(root), str(output), 2.5, sr, fit_timing=True)
    audio, _ = sf.read(output)
    assert np.all(audio[int(1.25 * sr):int(1.5 * sr)] > 0.1), "Simultaneous lines must play sequentially"
    (root / "line_002.wav").unlink()
    try:
        assemble_vocals_timeline(str(subtitles), str(root), str(output), 2.5, sr, fit_timing=True)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Missing dialogue must stop the render")
print("Timeline checks passed.")
