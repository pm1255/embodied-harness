"""Render a benchmark-first work order; no simulated progress or model calls."""
import argparse
import json
from pathlib import Path

from embodied_harness.rsi.core import digest, write_json
from embodied_harness.rsi.evolution import EvolutionStore


def export(manifest, order, output, history):
    manifest, order, output = Path(manifest), Path(order), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    store = EvolutionStore(history)
    tasks, work = json.loads(manifest.read_text()), json.loads(order.read_text())
    source = Path(__file__).resolve().parents[1]/'src/embodied_harness/rsi/curriculum.py'
    policy_artifacts = {'controller':store.put(source.read_bytes(),'text/x-python'),
                        'scope':store.put(manifest.read_bytes())}
    store.record('curriculum-policy/'+digest(policy_artifacts), 'curriculum_policy_changed', 'engineering_agent',
                 {'reason':'User requested existing benchmarks first, failure decomposition, task reuse, then gated difficulty expansion',
                  'historical_v1_results_unchanged':True, 'new_robot_episodes':0},
                 policy_artifacts)
    store.record('work-order/'+digest(work), 'work_order', 'experiment_controller',
                 {'mode':work['mode'], 'action':work['action']}, {'order':store.put(order.read_bytes())})
    lineage = store.verify()
    write_json(output/'tasks.json', tasks)
    write_json(output/'lineage.json', lineage)
    write_json(output/'next-work.json', work)
    data = {'tasks':tasks, 'order':work, 'lineage':lineage}
    template = source.parents[1]/'web/curriculum.html'
    (output/'index.html').write_text(template.read_text().replace('__DATA__',
        json.dumps(data,ensure_ascii=False).replace('<','\\u003c')),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','order','output','history'):
        p.add_argument(name)
    a=p.parse_args()
    export(a.manifest,a.order,a.output,a.history)
