"""Replay a frozen generated benchmark without any discovery or memory update."""
import argparse
import json
from pathlib import Path

from .core import digest, seal, write_json
from .experiment import make_jobs, run_jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--base-url', default='https://api.openai.com/v1')
    parser.add_argument('--workers', type=int, default=4, choices=range(1,9))
    args = parser.parse_args()
    manifest = json.loads(Path(args.benchmark).read_text(encoding='utf-8'))
    frozen = manifest['content']
    if digest(frozen) != manifest['sha256']:
        raise ValueError('Benchmark content hash mismatch')
    root = Path(args.output).resolve()
    if root.exists():
        raise ValueError('Use a fresh output directory for each benchmark repetition')
    root.mkdir(parents=True)
    config = {'model':args.model, 'base_url':args.base_url, 'max_decisions':8, 'max_control_ticks':400}
    seal(root/'benchmark.json', frozen)
    seal(root/'replay-protocol.json', {'benchmark_sha256':manifest['sha256'], 'config':config,
                                     'scope':'Frozen candidate four-arm evaluation; no memory writes'})
    rows = run_jobs(root, make_jobs(frozen['cases'], frozen['seeds'],
                                   ['baseline','memory','skills','combined'], 'heldout', 'heldout',
                                   config, frozen['candidate']), args.workers)
    write_json(root/'results.json', {'rows':rows, 'benchmark_sha256':manifest['sha256'], 'complete':True})


if __name__ == '__main__':
    main()
