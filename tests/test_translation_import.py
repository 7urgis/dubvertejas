"""Run: tools/Applio/.venv/bin/python tests/test_translation_import.py"""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dub_local import import_translation, imported_transcript

rows = [dict(idx=33, start_sec=1, end_sec=2)]
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/'translation.txt'
    cue = '33\n00:09:01,000 --> 00:09:02,000\n<i>Kodėl jos neveikia?!</i>\n\n'
    path.write_text(cue)
    assert import_translation(path, rows, rows) == {33:'Kodėl jos neveikia?!'}
    assert rows[0]['start_sec'] == 1
    for invalid in (cue+cue, cue.replace('33\n', '34\n')):
        path.write_text(invalid)
        try:
            import_translation(path, rows, rows)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid IDs accepted')
    path.write_text(cue.replace('33\n', '34\n'))
    try:
        import_translation(path, rows, rows+[dict(idx=34)])
    except ValueError:
        pass
    else:
        raise AssertionError('Missing dialogue accepted')
    original = [dict(idx=1,start_sec=1,end_sec=3,lt='Tik originalus tekstas.',en='Context only.'),
                dict(idx=2,start_sec=3,end_sec=5,lt='Antroji replika.')]
    path.write_text(json.dumps(original))
    result = imported_transcript(path,10)
    assert [r['lt'] for r in result] == ['Tik originalus tekstas.','Antroji replika.']
    assert result[1]['start_sec']==3 and result[1]['en']==''
    for changes in (dict(idx=1),dict(start_sec=2),dict(end_sec=11),dict(lt=''),dict(start_sec=float('nan'))):
        path.write_text(json.dumps([original[0],dict(original[1],**changes)]))
        try:
            imported_transcript(path,10)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Invalid transcript accepted: {changes}')
print('Translation import checks passed')
