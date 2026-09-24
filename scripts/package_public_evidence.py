"""Package full simulator frames with the already-sanitized public event streams."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def package(run, exported, destination):
    run, exported = Path(run).resolve(), Path(exported).resolve()
    data = json.loads((exported/'data.json').read_text())
    if not data['complete']:
        raise ValueError('Only a completed frozen experiment can be released')
    manifest = {'format_version':1, 'benchmark_sha256':data['benchmark_sha256'],
                'private_evolution_head':data['evolution']['head_hash'],
                'note':'Full recorded simulator frames. Provider identifiers removed from event streams. '
                       'Raw private trace hashes and sanitized hashes are distinguished in data.json.',
                'files':{}}
    with tarfile.open(destination, 'w:gz') as archive:
        def add_bytes(name, content):
            manifest['files'][name] = hashlib.sha256(content).hexdigest()
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(content), 0o644, 0
            archive.addfile(info, io.BytesIO(content))
        for row in data['rows']:
            root = (run/row['id']).resolve()
            root.relative_to(run)
            prefix = 'rsi-v1/'+row['id']
            trace = (exported/row['raw_trace']).resolve()
            trace.relative_to(exported)
            with gzip.open(trace, 'rb') as stream:
                events = stream.read()
            add_bytes(prefix+'/events.jsonl', events)
            add_bytes(prefix+'/result.json', json.dumps(row['result'], indent=2).encode())
            add_bytes(prefix+'/job.json', (root/'job.json').read_bytes())
            for path in sorted((root/'frames').glob('*.png')):
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != path.stem:
                    raise ValueError('A recorded frame failed content verification')
                add_bytes(prefix+'/frames/'+path.name, content)
        for name in ('benchmark.json','protocol.json','data.json','evolution.json','runtime.json','evaluation-code.json'):
            add_bytes('rsi-v1/'+name, (exported/name).read_bytes())
        add_bytes('rsi-v1/README.txt', b'Full sensor evidence for the published 72-episode RSI experiment.\n'
                  b'events.jsonl is sanitized; frames retain their original SHA-256 names.\n'
                  b'Camera scratch copies were byte-identical to recorded frames and are omitted.\n'
                  b'Rejected candidates remain in benchmark.json and data.json.\n')
        body=json.dumps(manifest,indent=2).encode()
        info=tarfile.TarInfo('MANIFEST.json')
        info.size, info.mode, info.mtime = len(body), 0o644, 0
        archive.addfile(info,io.BytesIO(body))
    print(json.dumps({'files':len(manifest['files']), 'sha256':hashlib.sha256(Path(destination).read_bytes()).hexdigest(),
                      'bytes':Path(destination).stat().st_size}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run')
    p.add_argument('exported')
    p.add_argument('destination')
    a=p.parse_args()
    package(a.run,a.exported,a.destination)
