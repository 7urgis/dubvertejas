#!/usr/bin/env python3
"""
subtitle_cleaner.py
Utility to clean and normalize Lithuanian text for speech synthesis (TTS).
Ensures numbers, abbreviations, and anime names are written phonetically in full words
so text-to-speech engines pronounce them with natural Lithuanian stress and phonetics.
"""

import re
import json

def normalize_lithuanian_dialogue(text: str) -> str:
    """
    Expands numbers, abbreviations, and common terms to phonetically
    accurate Lithuanian words for speech synthesis.
    """
    txt = text.strip()
    
    # Androids / Robots numbering
    txt = re.sub(r'Roboto\s+Nr\.\s*17', 'roboto numeris septyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Robotas\s+Nr\.\s*17', 'robotas numeris septyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Robotą\s+Nr\.\s*17', 'robotą numeris septyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'su\s+Nr\.\s*17', 'su robotu numeris septyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*17\s+ir\s+kitus', 'robotą numeris septyniolika ir kitus', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*17\s+ir\s+Nr\.\s*18', 'numeris septyniolika ir numeris aštuoniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'su\s+Nr\.\s*17\s+ir\s+Nr\.\s*18', 'su robotu numeris septyniolika ir numeriu aštuoniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*17', 'numeris septyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*18', 'numeris aštuoniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*16', 'numeris šešiolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*19', 'numeris devyniolika', txt, flags=re.IGNORECASE)
    txt = re.sub(r'Nr\.\s*20', 'numeris dvidešimt', txt, flags=re.IGNORECASE)

    # General abbreviations
    txt = re.sub(r'\bNr\.\s*', 'numeris ', txt)
    txt = re.sub(r'\bdr\.\s*', 'daktaras ', txt)
    txt = re.sub(r'\bprof\.\s*', 'profesorius ', txt)

    # Consistency in DBZ character names
    txt = txt.replace('Sėlas', 'Selas')
    txt = txt.replace('Celas', 'Selas')
    txt = txt.replace('nueis šunkiais', 'nueis šunkeliais')

    # Remove unexpected symbols that might confuse TTS
    txt = re.sub(r'[«»""„“]', '', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()

    return txt

def clean_json_transcript(input_path: str, output_path: str = None) -> list:
    """
    Cleans all Lithuanian dialogue lines in a structured JSON transcript file.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        if "lt" in item:
            item["lt"] = normalize_lithuanian_dialogue(item["lt"])

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Cleaned {len(data)} lines saved to {output_path}")

    return data

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        inp = sys.argv[1]
        out = sys.argv[2] if len(sys.argv) > 2 else inp
        clean_json_transcript(inp, out)
    else:
        sample = "Kova tarp Pikolo ir Roboto Nr. 17 jau prasidėjo. Selas ieško Nr. 18!"
        print("Original:", sample)
        print("Cleaned: ", normalize_lithuanian_dialogue(sample))
