import pytest

from embodied_harness.rsi.core import digest
from embodied_harness.rsi.curriculum import BenchmarkCurriculum, resolve_practice, validate_decomposition


def controller():
    return BenchmarkCurriculum([{'id':x,'environment':'fixture','instruction':x,'config':{}} for x in ('a','b')],
                               'r1',budget_hash='budget1',checkers=('sensor.distance','sensor.object_motion'))


def evidence(c, task, n=100, success=True, **extra):
    return [{'task_id':task,'split':'validation','episode_type':'full_task','variant':'original',
             'revision':'r1','definition_hash':digest(c.tasks[task]),'scope_hash':c.scope_hash,
             'budget_hash':c.budget_hash,'evaluator':'native','instance_id':f'{task}-{i}',
             'initial_state_hash':f'state-{task}-{i}','round_id':str(i%2),
             'status':'agent_finished','success':success,'episode_id':f'e-{task}-{i}',**extra} for i in range(n)]


def plan(validated=False):
    return {'parent_task':'a','revision':'r1','failure_evidence':'e-a-99','nodes':[
        {'id':'approach','capability':'reach','postcondition':'near object','checker':'sensor.distance',
         'validated':validated,'depends_on':[]},
        {'id':'grasp','capability':'grasp','postcondition':'object follows lift','checker':'sensor.object_motion',
         'validated':validated,'depends_on':['approach']}]}


def test_scope_gate_never_averages_away_failed_or_missing_tasks():
    c=controller()
    assert c.next_work([])['action']=='attempt_original'
    a=evidence(c,'a')
    assert not c.mastery(a)['all_mastered']
    assert c.next_work(a)['task_id']=='b'
    assert c.next_work(a+evidence(c,'b',success=False))['action']=='decompose_failed_original'
    assert c.next_work(a+evidence(c,'b'))['action']=='propose_harder_environment_or_task'


def test_practice_smoke_changed_env_and_old_revision_cannot_grant_mastery():
    c=controller()
    for changes in [{'episode_type':'subtask'}, {'episode_type':'smoke'}, {'variant':'easier'},
                    {'variant':'robustness'}, {'revision':'r0'}, {'definition_hash':'changed'},
                    {'budget_hash':'looser'}, {'evaluator':'model_self_rating'}, {'scope_hash':'smaller'}]:
        assert not c.mastery(evidence(c,'a',**changes)+evidence(c,'b',**changes))['all_mastered']
    repeated=evidence(c,'a',initial_state_hash='one-state')
    assert c.mastery(repeated)['tasks']['a']['independent_instances']==1
    with pytest.raises(ValueError,match='held-out'):
        c.mastery(evidence(c,'a',split='heldout'))


def test_decomposition_returns_to_original_instead_of_claiming_success():
    c=controller()
    rows=evidence(c,'a',success=False)+evidence(c,'b')
    assert c.next_work(rows,decompositions={'a':plan()})['action']=='resolve_and_practice_subtasks'
    assert c.next_work(rows,decompositions={'a':plan(True)})['action']=='resolve_and_practice_subtasks'
    reports=[{'node_id':n['id'],'checker':n['checker'],'decomposition_hash':digest(plan(True)),
              'revision':'r1','passed':True,'evaluator':'sensor_contract','trace_id':'trace/'+n['id']} for n in plan(True)['nodes']]
    order=c.next_work(rows,decompositions={'a':plan(True)},subtask_reports=reports)
    assert order['action']=='retest_original_end_to_end'
    assert not order['new_challenge_generation_allowed']
    cyclic=plan()
    cyclic['nodes'][0]['depends_on']=['grasp']
    with pytest.raises(ValueError,match='acyclic'):
        validate_decomposition(cyclic,'a')


def test_environment_changes_have_separate_purposes_and_scores():
    c=controller()
    rows=evidence(c,'a',success=False)
    assert c.environment_change('robustness_evaluation',rows,parent_task='a')['allowed']
    assert not c.environment_change('harder_challenge',rows)['allowed']
    found=resolve_practice('grasp',[{'id':'grasp-task','practice_for':['grasp']}],catalog_complete=True)
    assert found['action']=='reuse_existing_task'
    assert resolve_practice('grasp',[],catalog_complete=False)['action']=='complete_catalog_search'
    gap=resolve_practice('grasp',[],catalog_complete=True)
    practice=c.environment_change('missing_subtask_practice',rows,parent_task='a',gap=gap,decomposition=plan(),subgoal_id='grasp')
    assert practice['allowed'] and not practice['counts_as_original_mastery']
    with pytest.raises(ValueError):
        c.environment_change('missing_subtask_practice',rows,parent_task='a',gap=found)


def test_infrastructure_and_budget_are_not_capability_limits():
    c=controller()
    rows=evidence(c,'a',status='infrastructure_error')+evidence(c,'b')
    assert not c.mastery(rows)['tasks']['a']['mastered']
    assert c.next_work(rows)['action']=='repair_execution'
    assert c.next_work(rows,budget_remaining=False)['action']=='archive_budget_exhausted'


def test_blocked_task_is_deferred_but_never_dropped_from_gate():
    c=controller()
    order=c.next_work([],deferred_tasks={'a':'adapter unavailable'})
    assert order['task_id']=='b' and not order['new_challenge_generation_allowed']
    assert c.next_work(evidence(c,'b'),deferred_tasks={'a':'adapter unavailable'})['action']=='archive_blocked_frontier'


def test_a_tiny_bad_second_round_cannot_hide_under_a_good_average():
    c=controller()
    rows=evidence(c,'a',round_id='first')
    rows[-1]['round_id']='second'
    rows[-1]['success']=False
    assert not c.mastery(rows)['tasks']['a']['mastered']


def test_generated_practice_requires_real_parent_failure_and_exact_subgoal():
    c=controller()
    gap=resolve_practice('grasp',[],catalog_complete=True)
    with pytest.raises(ValueError,match='observed parent failure'):
        c.environment_change('missing_subtask_practice',evidence(c,'a'),parent_task='a',
                             gap=gap,decomposition=plan(),subgoal_id='grasp')
    with pytest.raises(ValueError,match='subgoal'):
        c.environment_change('missing_subtask_practice',evidence(c,'a',success=False),parent_task='a',
                             gap=gap,decomposition=plan(),subgoal_id='approach')


def test_mutating_frozen_scope_requires_a_new_version():
    c=controller()
    c.tasks['a']['instruction']='easier goal'
    with pytest.raises(ValueError,match='scope was modified'):
        c.mastery([])


def test_retry_failures_cannot_be_hidden_by_first_success():
    c=controller()
    good=evidence(c,'a')
    bad=evidence(c,'a',status='infrastructure_error',success=False)
    state=c.mastery(good+bad)['tasks']['a']
    assert not state['mastered'] and state['infrastructure_errors']==100
    assert state['successes']==0
    assert all(r['success'] for r in good)  # Input evidence is immutable.


def test_self_ratings_and_changed_budgets_do_not_authorize_practice():
    c=controller()
    gap=resolve_practice('grasp',[],catalog_complete=True)
    for changes in ({'evaluator':'model_self_rating'}, {'budget_hash':'looser'}):
        rows=evidence(c,'a',success=False,**changes)
        assert c.next_work(rows)['action']=='attempt_original'
        with pytest.raises(ValueError,match='observed parent failure'):
            c.environment_change('missing_subtask_practice',rows,parent_task='a',
                                 gap=gap,decomposition=plan(),subgoal_id='grasp')


def test_instance_aliases_cannot_create_independent_samples():
    c=controller()
    rows=evidence(c,'a',n=2)
    rows[1]['initial_state_hash']=rows[0]['initial_state_hash']
    assert c.mastery(rows)['tasks']['a']['independent_instances']==1
    changed=dict(rows[1],initial_state_hash='different-state')
    with pytest.raises(ValueError,match='different initial states'):
        c.mastery(rows+[changed])
