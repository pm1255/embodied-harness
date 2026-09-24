"""Read-only evolution inspection; never feeds final-test outcomes into learning."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from .evolution import EvolutionStore
from .frontier import FrontierPolicy


def inspect_evolution(run):
    run = Path(run)
    ledger = run/'evolution'
    events = EvolutionStore(ledger).verify() if ledger.exists() else []
    revisions, previous_memory, previous_skills = [], '', []
    for cycle in (1, 2):
        candidate_path = run/f'cycle-{cycle}-candidate.json'
        if not candidate_path.exists():
            continue
        candidate = json.loads(candidate_path.read_text())
        memory = (run/f'cycle-{cycle}-MEMORY.md').read_text()
        skills = candidate['content']['skills']
        gate_path = run/f'cycle-{cycle}-gate.json'
        gate = json.loads(gate_path.read_text()) if gate_path.exists() else None
        revisions.append({'cycle':cycle, 'candidate_hash':candidate['sha256'],
                          'gate':gate, 'memory_diff':'\n'.join(difflib.unified_diff(
                              previous_memory.splitlines(), memory.splitlines(),
                              fromfile=f'candidate-{cycle-1}', tofile=f'candidate-{cycle}', lineterm='')),
                          'skills_diff':'\n'.join(difflib.unified_diff(
                              json.dumps(previous_skills, indent=2, ensure_ascii=False).splitlines(),
                              json.dumps(skills, indent=2, ensure_ascii=False).splitlines(),
                              fromfile=f'candidate-{cycle-1}', tofile=f'candidate-{cycle}', lineterm=''))})
        previous_memory, previous_skills = memory, skills
    strata = {}
    for path in sorted(run.glob('episodes/*/*/result.json')):
        job = json.loads(path.with_name('job.json').read_text())
        if job['split'] not in ('discovery', 'validation'):
            continue
        key = f"{job['case']['id']} / {job['arm']} / {path.parent.parent.name}"
        result = json.loads(path.read_text())
        strata.setdefault(key, []).append({**result, 'split':job['split']})
    policy = FrontierPolicy()
    return {'events':events, 'head_hash':events[-1]['hash'] if events else None,
            'import_semantics':'Append order is archival observation order, not original experiment chronology.',
            'revisions':revisions,
            'frontiers':[{'stratum':key, **policy.assess(rows, task_validated=False)} for key,rows in strata.items()],
            'frontier_note':'Retrospective development-only diagnostic, not the policy used in v1. '
                            'No scene-specific positive witness was archived. Arms are not pooled. '
                            'The final test is excluded. This cannot establish a local plateau.'}
