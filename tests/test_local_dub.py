"""Run fully offline: unshare -Urn tools/Applio/.venv/bin/python tests/test_local_dub.py."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dub_local import subtitle_rows, dialogue_rows, checked_translations, conversation_blocks, unique_object, relevant_glossary

fixture = '''1
00:00:01,000 --> 00:00:02,000
{\\an8}<i>song romaji</i>

2
00:00:01,000 --> 00:00:02,000
<i>Song lyrics</i>

3
00:00:03,000 --> 00:00:05,000
Who are you?

4
00:00:03,000 --> 00:00:05,000
What?!
'''
rows = dialogue_rows(subtitle_rows(fixture))
assert [r['idx'] for r in rows] == [3, 4]
assert rows[0]['end_sec'] == rows[1]['start_sec'] == 4
assert 'Short Japanese reference' in rows[0]['review_note']

assert checked_translations({'translations':{'3':'Kas tu esi?','4':'Ką?!'}}, rows)[4]=='Ką?!'
try:json.loads('{"3":"Kas?","3":"Ką?!"}',object_pairs_hook=unique_object)
except ValueError:pass
else:raise AssertionError('Repeated JSON keys accepted')
assert 'Gokas' in relevant_glossary('| Goku, Son-kun | Gokas | Goko |', [{'en':'Has Son-kun arrived?'}])

# Missing/repeated IDs must never silently shift translated speech to another subtitle.
assert checked_translations({'translations':[{'idx':3,'lt':'Kas tu esi?'},{'idx':4,'lt':'Ką?!'}]}, rows)[3]=='Kas tu esi?'
for invalid in [
    {'translations':[{'idx':3,'lt':'Kas tu esi?'}]},
    {'translations':[{'idx':3,'lt':'Kas?'},{'idx':3,'lt':'Ką?!'}]},
    {'translations':[{'idx':3,'lt':''},{'idx':4,'lt':'Ką?!'}]},
    {'translations':[{'idx':True,'lt':'Kas?'},{'idx':4,'lt':'Ką?!'}]},
]:
    try:checked_translations(invalid,rows)
    except ValueError:pass
    else:raise AssertionError('Invalid translation accepted')
assert conversation_blocks([{'start_sec':0,'end_sec':1},{'start_sec':20,'end_sec':21}])==[(0,1),(1,2)]

with tempfile.TemporaryDirectory(prefix='dub-local-check-') as directory:
    out = Path(directory)
    srt = out/'english.srt'
    srt.write_text('1\n00:00:00,500 --> 00:00:02,200\nWho are you?\n')
    source = ROOT/'media/Dragon.Ball.Z.068.480p.DBox.DVD.REGRADE.LT-ENG-JAP.FLAC2.0.x264-SoM-7urgis.mkv'
    video = out/'smoke.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '228.4', '-i', str(source), '-i', str(srt),
        '-t', '3.4', '-map', '0:v:0', '-map', '0:2', '-map', '1:0', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-c:a', 'pcm_s16le', '-c:s', 'srt', '-metadata:s:a:0', 'language=jpn',
        '-metadata:s:s:0', 'language=eng', '-metadata:s:s:0', 'title=Basic Subtitles', str(video)], check=True)
    target = out/'dub'
    command = [sys.executable, str(ROOT/'dub_local.py'), '--video', str(video), '--out-dir', str(target)]
    subprocess.run(command+['--translate-only'], check=True)
    assert (target/'translation_review.html').is_file()
    assert not (target/'japanese.wav').exists(), 'Translation-only started audio processing'
    transcript = target/'transcript.json'
    reviewed = json.loads(transcript.read_text());reviewed[0]['lt']='Kas tu toks?'
    transcript.write_text(json.dumps(reviewed,ensure_ascii=False,indent=2))
    subprocess.run(command, check=True)
    result = json.loads((target/'verification.json').read_text())
    assert result['lines'] == 1 and result['decode_passed']
    assert abs(result['video_duration'] - 3.4) < .15
    assert (target/'index.html').is_file() and (target/'smoke.mkv.LT-Japanese-Voices.mp4').is_file()
    translation = json.loads((target/'transcript.json').read_text())[0]
    assert translation['lt']=='Kas tu toks?' and translation['reference_text'], 'Reviewed translation was overwritten'
    print('Offline end-to-end check passed:', translation['lt'], flush=True)
