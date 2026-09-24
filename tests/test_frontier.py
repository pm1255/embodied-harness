import pytest

from embodied_harness.rsi.frontier import FrontierPolicy, interval, paired_window


def attempts(n, successes=0, status='agent_finished'):
    return [{'split':'validation', 'status':status, 'success':i < successes} for i in range(n)]


def test_failure_is_not_a_capability_limit():
    policy = FrontierPolicy()
    assert policy.assess(attempts(2), task_validated=True)['state'] == 'insufficient_evidence'
    assert policy.assess(attempts(20), task_validated=False)['state'] == 'task_unverified'
    assert policy.assess(attempts(20, status='infrastructure_error'), task_validated=True)['state'] == 'infrastructure_limited'
    assert policy.assess(attempts(20), task_validated=True, budget_remaining=False)['state'] == 'budget_exhausted'
    assert policy.assess(attempts(20), task_validated=True)['state'] == 'beyond_current_frontier'
    assert policy.assess(attempts(20, 10), task_validated=True)['state'] == 'frontier'
    assert policy.assess(attempts(20, 20), task_validated=True)['state'] == 'consolidate'
    with pytest.raises(ValueError, match='development'):
        policy.assess([{'split':'heldout'}], task_validated=True)
    assert interval(0, 0) == [0, 1]


def window(look, n=200, wins=0):
    pairs = [{'instance_id':f'{look}-{i}', 'split':'validation',
              'baseline':{'success':True, 'status':'agent_finished'},
              'candidate':{'success':i < wins, 'status':'agent_finished'}} for i in range(n)]
    return paired_window(pairs, window_id=str(look), repair_class='tool' if look == 1 else 'memory', look=look)


def test_plateau_requires_diverse_measured_independent_repairs():
    policy = FrontierPolicy()
    measured = [window(i) for i in (1, 2, 3)]
    assert policy.assess(attempts(20), task_validated=True, repair_windows=measured)['state'] == 'local_plateau'
    duplicate = [measured[0], measured[1], measured[1]]
    assert policy.assess(attempts(20), task_validated=True, repair_windows=duplicate)['state'] != 'local_plateau'
    small = [window(i, 20, 20) for i in (1, 2, 3)]
    assert policy.assess(attempts(20), task_validated=True, repair_windows=small)['state'] != 'local_plateau'
    assert small[0]['gain_upper'] > .05  # No apparent gain is not evidence of no meaningful gain.
