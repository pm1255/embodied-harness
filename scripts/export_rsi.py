"""Export all episode results and two-view sampled videos, plus memory/skill provenance."""
from __future__ import annotations

import argparse
import copy
import gzip
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageOps
from embodied_harness.rsi.core import digest, write_json
from embodied_harness.rsi.inspection import inspect_evolution


def wilson(k, n):
    if n == 0:
        return [0, 1]
    z = 1.95996398454
    center = (k/n + z*z/(2*n)) / (1+z*z/n)
    radius = z * math.sqrt(k/n*(1-k/n)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-radius), min(1, center+radius)]


def statistics(rows):
    table = []
    heldout = [r for r in rows if r['split'] == 'heldout']
    for arm in ['baseline', 'memory', 'skills', 'combined']:
        subset = [r for r in heldout if r['arm'] == arm]
        n = len(subset)
        k = sum(r['result']['success'] for r in subset)
        table.append({'arm': arm, 'n': n, 'successes': k, 'wilson95': wilson(k, n),
                      'api_calls': sum(r['result'].get('api_calls', 0) for r in subset),
                      'input_tokens': sum(r['result'].get('input_tokens', 0) for r in subset),
                      'output_tokens': sum(r['result'].get('output_tokens', 0) for r in subset),
                      'infrastructure_errors': sum(r['result']['status']=='infrastructure_error' for r in subset),
                      'skill_calls': sum(r.get('skill_calls', 0) for r in subset),
                      'usage_missing_calls': sum(r.get('usage_missing_calls', 0) for r in subset),
                      'wall_seconds': sum(r['result'].get('wall_seconds', 0) for r in subset)})
    pairs = {}
    for row in heldout:
        pairs.setdefault((row['case']['id'], row['seed']), {})[row['arm']] = row['result']['success']
    positive = sum(x.get('combined') is True and x.get('baseline') is False for x in pairs.values())
    negative = sum(x.get('combined') is False and x.get('baseline') is True for x in pairs.values())
    discordant = positive + negative
    p = min(1, 2*sum(math.comb(discordant, i) for i in range(min(positive, negative)+1))/2**discordant) if discordant else 1
    return {'arms': table, 'paired_combined_baseline': {'wins': positive, 'losses': negative,
            'exact_mcnemar_p': p, 'note': 'Exploratory; six adaptively chosen families, two heldout seeds each. '
                                        'Wilson intervals do not adjust for within-family correlation.'}}


def video(events, source, target):
    obs_indices = [i for i, e in enumerate(events) if e['kind']=='observation']
    if not obs_indices:
        return []
    sampled = set(obs_indices[::max(1, len(obs_indices)//35)] + [obs_indices[-1]])
    selected = {'model_response', 'tool_start', 'skill_step', 'program_step', 'program_step_end', 'geometry', 'tool_end', 'episode_end', 'vla_prediction'}
    timeline, observation, call, geometry, primitive, program = [], None, None, None, None, None
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        for i, e in enumerate(events):
            kind, payload = e['kind'], e['payload']
            if kind == 'observation':
                observation = payload
            if kind == 'model_response':
                call = [{k:v for k,v in c.items() if k in ('name','arguments')} for c in payload.get('calls', [])]
                geometry = primitive = program = None
            if kind == 'program_step':
                program = payload
            if kind in ('skill_step', 'program_step', 'tool_start', 'vla_prediction'):
                primitive = payload
            if kind == 'geometry':
                geometry = payload
            if kind == 'control_tick' and 'policy_action' in payload:
                geometry = {'action_format': payload['action_format'], 'policy_action': payload['policy_action']}
            if kind == 'control_tick' and 'target_m' in payload:
                geometry = {k:payload[k] for k in ('target_m','actual_m','error_m') if k in payload}
            if observation is None or (kind not in selected and i not in sampled):
                continue
            frames = observation['frames']
            if any(f['name']=='head_camera' for f in frames):
                frames = sorted(frames, key=lambda x: {'head_camera':0,'front_camera':1}.get(x['name'],2))
            canvas = Image.new('RGB', (768, 336), '#101b29')
            draw = ImageDraw.Draw(canvas)
            for j, frame in enumerate(frames[:2]):
                with Image.open(source/frame['image_path']) as image:
                    canvas.paste(ImageOps.pad(image.convert('RGB'), (376, 296), color='#101b29'), (j*388, 24))
                draw.text((j*388+8, 6), frame['name'], fill='#b9d4ea')
            draw.text((8, 321), f"Recorded event {e['seq']} | {kind} | sampled replay, not real-time video", fill='#b9d4ea')
            canvas.save(tmp/f'{len(timeline):05d}.png')
            timeline.append({'seq':e['seq'], 'kind':kind, 'elapsed_s':e['elapsed_s'],
                             'call':copy.deepcopy(call), 'primitive':copy.deepcopy(primitive), 'program':copy.deepcopy(program),
                             'geometry':copy.deepcopy(geometry),
                             'result':payload if kind in ('tool_end','program_step_end','episode_end') else None})
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-framerate','3','-i',str(tmp/'%05d.png'),
                        '-y','-c:v','libx264','-pix_fmt','yuv420p','-crf','25','-movflags','+faststart',str(target)], check=True)
        if timeline:
            shutil.copyfile(tmp/'00000.png', target.with_suffix('.jpg.png'))
    return timeline


def export(source, destination, partial=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not partial:
        result = json.loads((source/'results.json').read_text())
        benchmark = json.loads((source/'benchmark.json').read_text())
    else:
        result = {'protocol':json.loads((source/'protocol.json').read_text())['content'],
                  'cases':[], 'cycles':[], 'rows':[]}
        for path in sorted(source.glob('cycle-*-scenarios.json')):
            result['cases'] += json.loads(path.read_text())['content']
        for path in sorted(source.glob('cycle-*-gate.json')):
            result['cycles'].append(json.loads(path.read_text()))
        for path in sorted(source.glob('episodes/*/*/result.json')):
            result['rows'].append({**json.loads(path.with_name('job.json').read_text()),
                                   'result':json.loads(path.read_text())})
        benchmark = (json.loads((source/'benchmark.json').read_text()) if (source/'benchmark.json').exists()
                     else {'sha256':'pending — heldout benchmark not frozen'})
    data = {'complete':not partial, 'protocol':result['protocol'], 'cases':result['cases'],
            'cycles':result['cycles'], 'benchmark_sha256':benchmark['sha256'],
            'memory_versions':[], 'rows':[]}
    for cycle in (1,2):
        if not (source/f'cycle-{cycle}-candidate.json').exists():
            continue
        candidate = json.loads((source/f'cycle-{cycle}-candidate.json').read_text())
        data['memory_versions'].append({'cycle':cycle, **candidate})
        shutil.copyfile(source/f'cycle-{cycle}-MEMORY.md', destination/f'cycle-{cycle}-MEMORY.md')
    for original in result['rows']:
        row = {k:original[k] for k in ('id','case','seed','split','arm','result')}
        root = source/row['id']
        event_path = root/'events.jsonl'
        events = [json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
        row['usage_missing_calls'] = sum(e['kind']=='model_request' for e in events) - sum(e['kind']=='model_response' and bool(e['payload'].get('usage')) for e in events)
        row['skill_calls'] = sum(e['kind']=='tool_start' and e['payload']['step']['tool'].startswith('skill_') for e in events)
        row['trace_sha256'] = digest(events)
        first = next((e['payload'] for e in events if e['kind']=='observation'), None)
        row['initial_sensor_hash'] = digest({
            'frames': {f['name']:f['sha256'] for f in first['frames']},
            'proprioception': first['proprioception']}) if first else None
        media = destination/'media'/row['id'].replace('/', '__')
        media.parent.mkdir(exist_ok=True)
        row['timeline'] = video(events, root, media.with_suffix('.mp4'))
        row['video'] = str(media.with_suffix('.mp4').relative_to(destination)) if row['timeline'] else None
        row['calls'], call_ids = [], {}
        for point in row['timeline']:
            calls = point.pop('call')
            key = digest(calls)
            if key not in call_ids:
                call_ids[key] = len(row['calls'])
                row['calls'].append(calls)
            point['call_id'] = call_ids[key]
        public_events = copy.deepcopy(events)
        for event in public_events:
            if event['kind'] == 'model_response':
                payload = event['payload']
                payload.pop('response_id', None)
                (payload.get('usage') or {}).pop('attribution', None)
                for call in payload.get('calls', []):
                    call.pop('id', None)
                    call.pop('call_id', None)
        raw_path = media.with_suffix('.jsonl.gz')
        with gzip.open(raw_path, 'wt', encoding='utf-8') as stream:
            for event in public_events:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        row['raw_trace'] = str(raw_path.relative_to(destination))
        row['public_trace_sha256'] = digest(public_events)
        data['rows'].append(row)
    data['statistics'] = statistics(data['rows'])
    grouped = {}
    for row in data['rows']:
        if row['split'] == 'heldout':
            grouped.setdefault(row['case']['id'] + '-s' + str(row['seed']), {})[row['arm']] = row['initial_sensor_hash']
    data['paired_reset_audit'] = {key:{'arms':values, 'identical': len(values)==4 and
                                         None not in values.values() and len(set(values.values()))==1}
                                  for key,values in grouped.items()}
    data['designer_attempts'] = [json.loads(p.read_text()) for p in sorted((source/'brain').glob('*attempt*.json'))]
    for attempt in data['designer_attempts']:
        attempt.pop('prompt', None)
    data['evolution'] = inspect_evolution(source)
    write_json(destination/'evolution.json', data['evolution'])
    write_json(destination/'data.json', data)
    for name in ['protocol.json','benchmark.json','MEMORY.md','designer-retry-amendment.json']:
        if (source/name).exists():
            shutil.copyfile(source/name, destination/name)
    template = Path(__file__).resolve().parents[1]/'src/embodied_harness/web/rsi.html'
    encoded = json.dumps(data, ensure_ascii=False).replace('<','\\u003c')
    (destination/'index.html').write_text(template.read_text().replace('__RSI_DATA__', encoded))
    print(json.dumps({'episodes':len(data['rows']), 'statistics':data['statistics']}, indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('--partial', action='store_true')
    args=parser.parse_args()
    export(args.source, args.destination, args.partial)
