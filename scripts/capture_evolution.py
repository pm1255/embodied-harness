"""Import existing real run artifacts without altering their contents or backdating events."""
import argparse
import json
from pathlib import Path

from embodied_harness.rsi.evolution import EvolutionStore
from embodied_harness.rsi.core import digest


def capture(run, destination, implementation_source=None, policy_runs=None):
    run = Path(run)
    store = EvolutionStore(destination)
    for name in ['protocol.json','designer-retry-amendment.json','evaluation-code.json',
                 'benchmark.json','results.json','runtime.json','archive-frame-audit.json']:
        path = run/name
        if path.exists():
            store.record(name, 'protocol', 'experiment_operator', {'source':name},
                         {'document':store.put(path.read_bytes())})
    for cycle in [1,2]:
        for suffix,kind in [('scenarios','tasks_proposed'),('rejected-reflection','proposal_rejected'),
                            ('candidate','candidate_snapshot'),('gate','promotion_decision')]:
            name = f'cycle-{cycle}-{suffix}.json'
            path = run/name
            if not path.exists():
                continue
            payload = {'cycle':cycle,'source':name,'parent_approved_snapshot':
                       'baseline' if cycle==1 else 'cycle-1-gate.json'}
            actor = 'experiment_brain' if suffix in ('scenarios','candidate') else 'experiment_evaluator'
            store.record(name, kind, actor, payload, {'document':store.put(path.read_bytes())})
        path = run/f'cycle-{cycle}-MEMORY.md'
        if path.exists():
            store.record(path.name, 'memory_document', 'experiment_brain', {'cycle':cycle},
                         {'markdown':store.put(path.read_bytes(), 'text/markdown')})
    for path in sorted((run/'brain').glob('*attempt*.json')):
        data=json.loads(path.read_text())
        if data.get('status')=='started':
            continue
        store.record(path.name, 'designer_attempt', 'experiment_brain',
                     {'status':data['status'], 'source':str(path.relative_to(run))},
                     {'record':store.put(path.read_bytes())})
    for path in sorted((run/'episodes').glob('*/*/result.json')):
        job=json.loads(path.with_name('job.json').read_text())
        artifacts={'result':store.put(path.read_bytes()),'inputs':store.put(path.with_name('job.json').read_bytes())}
        trace=path.with_name('events.jsonl')
        if trace.exists():
            artifacts['trace']=store.put(trace.read_bytes(),'application/x-ndjson')
        store.record(job['id'], 'rollout', 'experiment_runtime',
                     {'split':job['split'],'arm':job['arm'],'case_id':job['case']['id'],'seed':job['seed']},artifacts)
    if policy_runs:
        policy_root = Path(policy_runs)
        for trace in sorted(policy_root.glob('**/events.jsonl')):
            relative = str(trace.parent.relative_to(policy_root))
            summary = trace.with_name('summary.json')
            refs = {'trace':store.put(trace.read_bytes(), 'application/x-ndjson')}
            payload = {'run':relative, 'scope':'separate_tool_diagnostic_not_RSI_gain'}
            if summary.exists():
                refs['summary'] = store.put(summary.read_bytes())
                result = json.loads(summary.read_text())
                payload.update({k:result[k] for k in ('status','success','environment_success','control_ticks')})
            else:
                payload['status'] = 'no_final_summary_preserved'
            store.record('specialist/'+relative, 'tool_diagnostic', 'experiment_runtime', payload, refs)
    if implementation_source:
        source = Path(implementation_source)
        refs = {str(p.relative_to(source)):store.put(p.read_bytes(), 'text/x-python')
                for p in sorted((source/'src/embodied_harness/rsi').glob('*.py'))}
        store.record('engineering/'+digest(refs), 'implementation_snapshot', 'coding_agent',
                     {'purpose':'Evolution archive and frontier tooling',
                      'used_by_v1_experiment':False,
                      'note':'Engineering work, not an autonomous modification by the experiment brain'}, refs)
    print(json.dumps({'events':len(store.verify()),'root':str(Path(destination))}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run')
    p.add_argument('output')
    p.add_argument('--implementation-source')
    p.add_argument('--policy-runs')
    a=p.parse_args()
    capture(a.run,a.output,a.implementation_source,a.policy_runs)
