#!/usr/bin/env python3
"""Move recorded Lithuanian phrases to matching Japanese subtitle windows without rewriting them."""
import argparse
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

from dub_local import dialogue_rows, imported_transcript, save_json, subtitle_rows


def apply_alignment(rows, cues, mapping):
    if not isinstance(mapping,dict) or set(mapping)!={str(r['idx']) for r in rows}:
        raise ValueError('Alignment must cover every Lithuanian phrase exactly once')
    positions = {r['idx']:i for i,r in enumerate(cues)}
    spans = [];previous = (-1,-1)
    for r in rows:
        pair = mapping[str(r['idx'])]
        if not isinstance(pair,list) or len(pair)!=2 or any(type(i) is not int or i not in positions for i in pair):
            raise ValueError('Alignment endpoints must be source cue IDs')
        first,last = (positions[i] for i in pair)
        if first>last or first<previous[0] or last<previous[1]:
            previous_ids=[cues[i]['idx'] for i in previous] if previous[0]>=0 else []
            raise ValueError(f'Phrase {r["idx"]} maps to {pair}, going backwards after {previous_ids}. Reconsider BOTH this phrase and the preceding phrase: the preceding match may need an earlier cue. Preserve dialogue order.')
        spans.append((r,first,last));previous=(first,last)
    groups=[]
    for item in spans:
        if groups and item[1]<=max(x[2] for x in groups[-1]):groups[-1].append(item)
        else:groups.append([item])
    aligned=[]
    for group in groups:
        start=cues[group[0][1]]['start_sec'];end=cues[max(x[2] for x in group)]['end_sec']
        total=sum(r['end_sec']-r['start_sec'] for r,_,_ in group)
        cursor=start
        for r,first,last in group:
            stop=cursor+(end-start)*(r['end_sec']-r['start_sec'])/total
            if r is group[-1][0]:stop=end
            aligned.append(dict(r,start_sec=cursor,end_sec=stop,
                original_start_sec=r['start_sec'],original_end_sec=r['end_sec'],
                source_ids=[c['idx'] for c in cues[first:last+1]],en=' '.join(c['en'] for c in cues[first:last+1]),
                review_note=r.get('review_note','')+' Timing matched to Japanese dialogue; verify meaning and speaker.'))
            cursor=stop
    return aligned


def tokens(text):
    plain=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c))
    stop=set('ir kad jis tai tu as mes jus i su uz ar kaip yra jo ji jos ju jau bet dar vis savo mano tavo'.split())
    return {w[:5] for w in re.findall(r'\w+',plain) if w not in stop} or set(re.findall(r'\w+',plain))


def match_dialogue(rows,cues,hints):
    # ponytail: lexical matching is conservative; synonyms/unclear ASR stay Japanese, not guessed dialogue.
    documents=[tokens(hints.get(c['idx'],'')) for c in cues]
    vocabulary=set().union(*documents)
    weights={t:1+math.log((len(cues)+1)/(1+sum(t in d for d in documents))) for t in vocabulary}
    states={-1:0};history=[]
    for row in rows:
        original=tokens(row['lt']);middle=(row['start_sec']+row['end_sec'])/2
        candidates=[]
        for first,cue in enumerate(cues):
            if abs(cue['start_sec']-middle)>45:continue
            for last in range(first,min(first+3,len(cues))):
                target=set().union(*documents[first:last+1])
                if not target:continue
                common=sum(weights.get(t,3)*max((difflib.SequenceMatcher(None,t,u).ratio() for u in target),default=0) for t in original
                           if max((difflib.SequenceMatcher(None,t,u).ratio() for u in target),default=0)>=.75)
                denominator=sum(weights.get(t,3) for t in original)+sum(weights.get(t,3) for t in target)
                lexical=min(1,2*common/max(denominator,1))
                text=' '.join(hints.get(c['idx'],'') for c in cues[first:last+1])
                score=.8*lexical+.2*difflib.SequenceMatcher(None,row['lt'].lower(),text.lower()).ratio()
                shift=abs((cue['start_sec']+cues[last]['end_sec'])/2-middle)
                candidates.append((first,last,score,shift))
        current={};links={}
        for first,last,confidence,shift in candidates:
            for previous,value in states.items():
                if previous>first:continue
                value+=confidence-.07*max(0,first-previous-1)-.1*min(shift/20,1)-.025*(last-first)
                if value>current.get(last,float('-inf')):
                    current[last]=value;links[last]=(previous,first,last,confidence,shift)
        if not current:raise ValueError(f'No ordered match near phrase {row["idx"]}; review its timing')
        states=current;history.append(links)
    endpoint=max(states,key=states.get);mapping={};scores={}
    for row,links in zip(reversed(rows),reversed(history)):
        previous,first,last,confidence,shift=links[endpoint]
        mapping[str(row['idx'])]=[cues[first]['idx'],cues[last]['idx']]
        scores[str(row['idx'])]=dict(score=round(confidence,3),shift_seconds=round(shift,2),use_lithuanian=confidence>=.35)
        endpoint=previous
    return mapping,scores


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcript',type=Path,required=True)
    parser.add_argument('--english-subtitles',type=Path,required=True)
    parser.add_argument('--matching-subtitles',type=Path,required=True,help='Lithuanian cue meanings for matching only; their wording is never spoken')
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Use a fresh alignment directory')
    rows=imported_transcript(args.transcript,float('inf'));cues=dialogue_rows(subtitle_rows(args.english_subtitles.read_text()))
    if len({r['idx'] for r in cues})!=len(cues):raise ValueError('Source subtitle IDs must be unique')
    hints={r['idx']:r['en'] for r in subtitle_rows(args.matching_subtitles.read_text())}
    mapping,scores=match_dialogue(rows,cues,hints)
    aligned=apply_alignment(rows,cues,mapping)
    selected=[r for r in aligned if scores[str(r['idx'])]['use_lithuanian']]
    skipped=[dict(r,alignment_score=scores[str(r['idx'])]['score'],reason='Uncertain match: keep original Japanese audio') for r in aligned if not scores[str(r['idx'])]['use_lithuanian']]
    if not selected:raise ValueError('No confident matches; no dub transcript written')
    originals={r['idx']:r['lt'] for r in rows}
    assert all(r['lt']==originals[r['idx']] for r in selected)
    digest=hashlib.sha256(args.transcript.read_bytes()+args.english_subtitles.read_bytes()+args.matching_subtitles.read_bytes()).hexdigest()
    save_json(out/'alignment.json',dict(input_digest=digest,alignments=mapping,scores=scores,method='ordered lexical matching; uncertain phrases remain Japanese',version=2))
    save_json(out/'skipped_phrases.json',skipped)
    save_json(out/'transcript.json',selected)
    print(f'Aligned {len(selected)} phrases; {len(skipped)} uncertain phrases remain Japanese. {out/"transcript.json"}',flush=True)


if __name__=='__main__':main()
