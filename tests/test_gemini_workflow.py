"""Run: tools/Applio/.venv/bin/python tests/test_gemini_workflow.py"""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dub_gemini import episode_files, output_directory, translation_file

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'media').mkdir()
    video=root/'media/Dragon.Ball.Z.149.480p.LT-ENG-JAP.test.mkv';video.write_bytes(b'video')
    (root/'media/Dragon.Ball.Z.149.DBox.Remastered.LT-AI.mkv').write_bytes(b'accepted')
    found,folder=episode_files(149,root)
    assert found==video and folder==root/'data/gemini/149'
    folder.mkdir(parents=True)
    text=folder/'translation.srt';text.write_text('Original Gemini text')
    assert translation_file(folder)==text
    first=output_directory(149,video,text,root)
    assert output_directory(149,video,text,root)==first
    text.write_text('Changed Gemini text')
    assert output_directory(149,video,text,root)!=first
    (folder/'translation.txt').write_text('Ambiguous second file')
    try:translation_file(folder)
    except ValueError:pass
    else:raise AssertionError('Ambiguous translations accepted')
    for episode in (0,1000,150):
        try:episode_files(episode,root)
        except ValueError:pass
        else:raise AssertionError('Invalid/missing episode accepted')
print('Gemini workflow checks passed')
