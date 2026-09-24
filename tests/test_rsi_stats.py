import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('export_rsi', Path(__file__).parents[1]/'scripts/export_rsi.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_all_failures_remain_in_statistical_denominator():
    rows = []
    for seed in [101,102]:
        for arm in ['baseline','memory','skills','combined']:
            rows.append({'split':'heldout','case':{'id':'c1t1'}, 'seed':seed, 'arm':arm,
                         'result':{'success':arm=='combined' and seed==101,
                                   'status':'infrastructure_error' if seed==102 else 'agent_finished',
                                   'api_calls':2}, 'skill_calls':int(arm=='combined')})
    result = module.statistics(rows)
    combined = next(r for r in result['arms'] if r['arm']=='combined')
    assert combined['n']==2 and combined['successes']==1
    assert combined['infrastructure_errors']==1
    assert result['paired_combined_baseline']['wins']==1
    assert result['paired_combined_baseline']['losses']==0
    low, high = module.wilson(0,12)
    assert low==0 and .24 < high < .25
