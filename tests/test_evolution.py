import json

import pytest

from embodied_harness.rsi.candidates import CandidateArchive
from embodied_harness.rsi.evolution import EvolutionStore


def test_append_only_idempotent_and_tamper_detected(tmp_path):
    store = EvolutionStore(tmp_path)
    ref = store.put(b'failed attempt', 'text/plain')
    row = store.record('r1', 'rejected', 'evaluator', {'accepted':False}, {'result':ref})
    assert store.record('r1', 'rejected', 'evaluator', {'accepted':False}, {'result':ref}) == row
    with pytest.raises(ValueError, match='rewritten'):
        store.record('r1', 'accepted', 'evaluator', {'accepted':True})
    (tmp_path/'objects'/ref['sha256']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='modified'):
        store.verify()


def test_broken_lineage_is_detected(tmp_path):
    store = EvolutionStore(tmp_path)
    store.record('a', 'fact', 'runtime', {})
    row = store.record('b', 'hypothesis', 'brain', {})
    store.ledger.write_text(json.dumps(row)+'\n')
    with pytest.raises(ValueError, match='lineage'):
        store.verify()


def test_code_stays_staged_and_rejections_do_not_activate(tmp_path):
    store = EvolutionStore(tmp_path)
    store.record('run/dev1', 'rollout', 'runtime', {'split':'discovery'})
    store.record('run/test1', 'rollout', 'runtime', {'split':'heldout'})
    archive = CandidateArchive(store)
    args = {'parent':'baseline', 'changes':{'tools/contact.py':'raise RuntimeError("must not execute")'},
            'hypothesis':'Retry contact detection', 'evidence':['run/dev1']}
    row = archive.propose(**args)
    assert row['payload']['execution_status'] == 'staged_not_executed'
    assert archive.active_revision() == 'baseline'
    report = {'split':'validation', 'candidate_id':row['event_id']}
    rejected = archive.record_evaluation(row['event_id'], report)
    with pytest.raises(ValueError):
        archive.activate(rejected['event_id'])
    for key in ('contract_passed','transfer_passed','retention_passed','budget_passed',
                'independent_evaluator','evidence_verified'):
        report[key] = True
    accepted = archive.record_evaluation(row['event_id'], report)
    archive.activate(accepted['event_id'])
    archive.rollback('baseline', 'Later regression')
    assert archive.active_revision() == 'baseline'
    assert len([r for r in store.verify() if r['kind'] == 'candidate_evaluated']) == 2
    with pytest.raises(ValueError, match='Held-out'):
        archive.propose(**{**args, 'evidence':['run/test1']})
    with pytest.raises(ValueError, match='mutable'):
        archive.propose(**{**args, 'changes':{'tools/../../evaluator.py':'bad'}})


def test_inspector_never_pools_candidate_revisions_or_reads_heldout(tmp_path):
    from embodied_harness.rsi.inspection import inspect_evolution
    for phase, split in [('cycle-1-validate','validation'), ('cycle-2-validate','validation'), ('heldout','heldout')]:
        root = tmp_path/'episodes'/phase/'a'
        root.mkdir(parents=True)
        (root/'job.json').write_text(json.dumps({'case':{'id':'a'},'arm':'combined','split':split}))
        (root/'result.json').write_text(json.dumps({'status':'agent_finished','success':split == 'heldout'}))
    view = inspect_evolution(tmp_path)
    assert len(view['frontiers']) == 2
    assert all(row['attempts'] == 1 for row in view['frontiers'])
    assert all('heldout' not in row['stratum'] for row in view['frontiers'])
