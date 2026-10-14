"""Run: tools/Applio/.venv/bin/python tests/test_dub_alignment.py"""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from align_lt_dub import apply_alignment, match_dialogue
from dub_local import reference_cue

rows=[dict(idx=42,start_sec=375.93,end_sec=378.07,lt='Tavo sėbrai dar gyvi.'),
      dict(idx=43,start_sec=378.73,end_sec=381.09,lt='Pasiimk juos ir nešdinkitės.')]
cues=[dict(idx=76,start_sec=376.33,end_sec=379.36,en='Give up this fight.'),
      dict(idx=77,start_sec=384.46,end_sec=387.54,en='Your friends are still alive.'),
      dict(idx=78,start_sec=387.54,end_sec=389.87,en='Take them and leave.')]
aligned=apply_alignment(rows,cues,{'42':[77,77],'43':[78,78]})
assert aligned[1]['start_sec']==387.54
assert aligned[1]['end_sec']==389.87
assert aligned[0]['lt']==rows[0]['lt'] and aligned[1]['lt']==rows[1]['lt']
assert rows[1]['start_sec']==378.73
assert reference_cue(aligned[1],cues)['idx']==78
shared=apply_alignment(rows,cues,{'42':[77,77],'43':[77,78]})
assert shared[0]['end_sec']==shared[1]['start_sec']
assert shared[1]['end_sec']==389.87
mapping,scores=match_dialogue(rows,cues,{76:'Nutraukite šią kovą.',77:'Tavo draugai dar gyvi.',78:'Pasiimk juos ir nešdinkitės.'})
assert mapping['43']==[78,78] and scores['43']['use_lithuanian']
assert mapping['42']==[77,77]
assert rows[1]['lt']=='Pasiimk juos ir nešdinkitės.'
for invalid in ({'42':[77,77]}, {'42':[78,78],'43':[77,77]}, {'42':[77,77],'43':[78,999]}, {'42':[True,77],'43':[78,78]}):
    try:apply_alignment(rows,cues,invalid)
    except ValueError:pass
    else:raise AssertionError(f'Invalid mapping accepted: {invalid}')
print('Dialogue timing alignment checks passed')
