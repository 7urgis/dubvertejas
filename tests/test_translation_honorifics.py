"""Run: tools/Applio/.venv/bin/python tests/test_translation_honorifics.py"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dub_local import normalize_honorifics

glossary = (ROOT/'data/context/dragon_ball_lt.md').read_text()
raw = {146: 'Po to, kai Frizas-sama išgirs slaptažodį nuo namekų...',
       147: 'Frizo-sama! Pikolas-san! Gokai-kun!',
       148: 'Son-kun? Unknown-sama?', 149: 'Š-Šenronas...'}
clean = normalize_honorifics(raw, glossary)
assert clean[146] == 'Po to, kai Frizas išgirs slaptažodį nuo namekų...'
assert clean[147] == 'Frizo! Pikolas! Gokai!'
assert clean[148] == raw[148]  # Aliases need contextual translation, not blind replacement.
assert clean[149] == raw[149]
assert raw[146].startswith('Po to, kai Frizas-sama')
assert normalize_honorifics(clean, glossary) == clean
print('Honorific normalization checks passed')
