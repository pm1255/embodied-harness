"""Benchmark-first curriculum controller, independent of the proposer and simulator.

This module schedules work and validates transitions. It never grants mastery on
an LLM's self-rating, a smoke test, an easier scene, or a successful subtask.
Simulator runners supply evidence; executable decomposition checkers remain an
adapter responsibility. The historical v1 discovery experiment is unchanged.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from statistics import NormalDist

from .core import digest, write_json
from .frontier import INFRASTRUCTURE, VALID_OUTCOMES


@dataclass(frozen=True)
class MasteryPolicy:
    min_instances: int = 20
    min_rounds: int = 2
    success_lower_bound: float = .8
    family_error: float = .05
    max_infrastructure_fraction: float = .05

    def __post_init__(self):
        if self.min_instances < 2 or self.min_rounds < 2:
            raise ValueError('Mastery requires multiple instances and evaluation rounds')
        if not 0 < self.success_lower_bound < 1 or not 0 < self.family_error < 1:
            raise ValueError('Invalid confidence or success threshold')
        if not 0 <= self.max_infrastructure_fraction < 1:
            raise ValueError('Invalid reliability threshold')


def task_definition(case):
    return {'id':case['id'], 'environment':case['environment'],
            'instruction':case['instruction'], 'config':copy.deepcopy(case['config'])}


class BenchmarkCurriculum:
    def __init__(self, cases, revision, *, budget_hash, policy=None, checkers=()):
        if not cases or len({c['id'] for c in cases}) != len(cases):
            raise ValueError('Freeze a nonempty benchmark scope with unique task IDs')
        self.checkers = set(checkers)
        self.tasks = {c['id']:task_definition(c) for c in cases}
        self.revision, self.budget_hash = revision, budget_hash
        self.policy = policy or MasteryPolicy()
        self.scope_hash = digest(self.tasks)

    def mastery(self, evidence):
        """Fresh original-task validation, exact revision and protocol only.

        instance_id and initial_state_hash are supplied by the trusted evaluator.
        Repeated scene states are displayed as attempts, but cannot inflate the
        independent-instance floor. Unknown/infra outcomes count as failures.
        Wilson bounds use a Bonferroni adjustment across the frozen task scope;
        they are diagnostics, not a sequential-trial significance guarantee.
        """
        if digest(self.tasks) != self.scope_hash:
            raise ValueError('Frozen benchmark scope was modified')
        if any(r.get('split') == 'heldout' for r in evidence):
            raise ValueError('Keep final held-out tests outside the adaptive curriculum')
        result = {}
        z = NormalDist().inv_cdf(1-self.policy.family_error/(2*len(self.tasks)))
        for task_id, task in self.tasks.items():
            rows = [r for r in evidence if r.get('task_id') == task_id
                    and r.get('split') == 'validation' and r.get('episode_type') == 'full_task'
                    and r.get('variant') == 'original' and r.get('revision') == self.revision
                    and r.get('definition_hash') == digest(task) and r.get('budget_hash') == self.budget_hash
                    and r.get('evaluator') == 'native' and r.get('scope_hash') == self.scope_hash]
            seen_instances, seen_states, instance_states, unique = {}, {}, {}, []
            for row in rows:
                required = ('instance_id', 'initial_state_hash', 'round_id', 'status', 'success')
                if any(key not in row for key in required) or type(row['success']) is not bool:
                    raise ValueError('Incomplete evaluator evidence')
                if not row['initial_state_hash'] and row['status'] in VALID_OUTCOMES:
                    raise ValueError('Valid physical trials need an initial-state fingerprint')
                instance = row['instance_id']
                state_hash = row['initial_state_hash']
                if instance in instance_states and instance_states[instance] != state_hash:
                    raise ValueError('An instance ID cannot refer to different initial states')
                instance_states[instance] = state_hash
                old = seen_instances.get(row['instance_id'], seen_states.get(row['initial_state_hash']))
                if old is not None:
                    # Repeating a successful state cannot hide later failures or gain sample count.
                    unique[old]['success'] = unique[old]['success'] and row['success'] and row['status'] in VALID_OUTCOMES
                    seen_instances[instance] = old
                    continue
                seen_instances[row['instance_id']] = len(unique)
                if row['initial_state_hash']:
                    seen_states[row['initial_state_hash']] = len(unique)
                unique.append(dict(row))
            n = len(unique)
            successes = sum(r['success'] and r['status'] in VALID_OUTCOMES for r in unique)
            infra = sum(r['status'] not in VALID_OUTCOMES for r in rows)
            physical_instances = sum(bool(r['initial_state_hash']) for r in unique)
            if n:
                rate = successes/n
                lower = ((rate+z*z/(2*n))-z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n)))/(1+z*z/n)
            else:
                lower = 0
            rounds = len({r['round_id'] for r in unique})
            by_round = {}
            for r in unique:
                by_round.setdefault(r['round_id'], []).append(r)
            stable = all(len(group) >= math.ceil(self.policy.min_instances/self.policy.min_rounds)
                         and sum(r['success'] and r['status'] in VALID_OUTCOMES for r in group)/len(group)
                         >= self.policy.success_lower_bound for group in by_round.values())
            mastered = (stable and physical_instances >= self.policy.min_instances and rounds >= self.policy.min_rounds
                        and lower >= self.policy.success_lower_bound
                        and infra/len(rows) <= self.policy.max_infrastructure_fraction)
            result[task_id] = {'attempts':len(rows), 'independent_instances':physical_instances, 'scored_instances':n, 'successes':successes,
                               'rounds':rounds, 'infrastructure_errors':infra,
                               'simultaneous_wilson_lower':max(0, lower), 'mastered':bool(mastered)}
        return {'scope_hash':self.scope_hash, 'revision':self.revision, 'budget_hash':self.budget_hash,
                'policy':asdict(self.policy), 'tasks':result,
                'all_mastered':all(r['mastered'] for r in result.values())}

    def next_work(self, evidence, *, decompositions=None, subtask_reports=(), budget_remaining=True, deferred_tasks=None):
        """Issue a work order. Practice successes never replace original-task results."""
        readiness = self.mastery(evidence)
        deferred_tasks = deferred_tasks or {}
        if not set(deferred_tasks) <= set(self.tasks):
            raise ValueError('Cannot defer a task outside the frozen scope')
        common = {'deferred_tasks':deferred_tasks, 'readiness':readiness, 'new_challenge_generation_allowed':readiness['all_mastered']}
        if not budget_remaining:
            return {**common, 'action':'archive_budget_exhausted', 'task_id':None}
        if readiness['all_mastered']:
            return {**common, 'action':'propose_harder_environment_or_task', 'task_id':None,
                    'requirements':['Create a separate versioned challenge track',
                                    'Retain original-suite regression tests',
                                    'Validate task feasibility and independent success semantics']}
        history = [r for r in evidence if r.get('task_id') in self.tasks and r.get('revision') == self.revision
                   and r.get('scope_hash') == self.scope_hash and r.get('budget_hash') == self.budget_hash
                   and r.get('episode_type') == 'full_task' and r.get('variant') == 'original'
                   and r.get('definition_hash') == digest(self.tasks.get(r.get('task_id')))
                   and r.get('evaluator') == 'native'
                   and r.get('split') in ('development','validation')]
        # First cover the selected scope; missing/blocked adapters cannot vanish from it.
        for task_id in self.tasks:
            if task_id not in deferred_tasks and not any(r['task_id'] == task_id for r in history):
                return {**common, 'action':'attempt_original', 'task_id':task_id}
        for task_id, state in readiness['tasks'].items():
            if state['mastered'] or task_id in deferred_tasks:
                continue
            latest = [r for r in history if r['task_id'] == task_id][-1]
            if latest['status'] in INFRASTRUCTURE or latest['status'] not in VALID_OUTCOMES:
                return {**common, 'action':'repair_execution', 'task_id':task_id}
            if latest['success']:
                return {**common, 'action':'validate_original_fresh_instances', 'task_id':task_id}
            decomposition = (decompositions or {}).get(task_id)
            if not decomposition:
                return {**common, 'action':'decompose_failed_original', 'task_id':task_id,
                        'failure_evidence':latest.get('episode_id'),
                        'requirements':['Use observable subgoal postconditions and a dependency DAG',
                                        'Separate contact/grasp verification from arm motion',
                                        'Search existing benchmark tasks before creating practice tasks']}
            validate_decomposition(decomposition, task_id)
            if decomposition.get('revision') != self.revision:
                return {**common, 'action':'revalidate_decomposition', 'task_id':task_id}
            failed_ids = {r.get('episode_id') for r in history if r['task_id'] == task_id
                          and r['success'] is False and r['status'] in VALID_OUTCOMES}
            if decomposition['failure_evidence'] not in failed_ids:
                raise ValueError('Decomposition must reference an actual failure of this parent revision')
            missing = [n['checker'] for n in decomposition['nodes'] if n['checker'] not in self.checkers]
            if missing:
                return {**common, 'action':'implement_or_bind_subgoal_checkers', 'task_id':task_id,
                        'missing_checkers':sorted(set(missing))}
            verified = {r['node_id'] for r in subtask_reports
                        if r.get('decomposition_hash') == digest(decomposition) and r.get('revision') == self.revision
                        and r.get('evaluator') in ('sensor_contract','native_subtask')
                        and r.get('passed') is True and r.get('trace_id')
                        and any(n['id'] == r.get('node_id') and n['checker'] == r.get('checker')
                                for n in decomposition['nodes'])}
            if not all(n['id'] in verified for n in decomposition['nodes']):
                return {**common, 'action':'resolve_and_practice_subtasks', 'task_id':task_id,
                        'decomposition':decomposition}
            return {**common, 'action':'retest_original_end_to_end', 'task_id':task_id,
                    'requirements':['Use the original reset distribution and native predicate',
                                    'No intermediate reset, privileged state injection, or easier physics']}
        return {**common, 'action':'archive_blocked_frontier', 'task_id':None,
                'requirements':['Blocked tasks remain in the mastery denominator',
                                'Resume when the recorded infrastructure or capability boundary changes']}

    def environment_change(self, purpose, evidence, *, parent_task=None, gap=None, decomposition=None, subgoal_id=None):
        """Classify environmental interventions before executing them."""
        if purpose == 'robustness_evaluation':
            if parent_task not in self.tasks:
                raise ValueError('Robustness tests need an original parent task')
            return {'allowed':True, 'track':'robustness', 'counts_as_original_mastery':False,
                    'requirements':['Preserve task goal and native success predicate',
                                    'Record changes and test unseen intervention instances',
                                    'Report separately from official/original benchmark scores']}
        if purpose == 'missing_subtask_practice':
            if parent_task not in self.tasks or not gap or gap.get('action') != 'create_missing_practice':
                raise ValueError('Practice generation requires an audited catalog gap for a failed parent')
            validate_decomposition(decomposition or {}, parent_task)
            failures = {r.get('episode_id') for r in evidence if r.get('task_id') == parent_task
                        and r.get('split') in ('development','validation') and r.get('success') is False
                        and r.get('variant') == 'original' and r.get('episode_type') == 'full_task'
                        and r.get('revision') == self.revision and r.get('scope_hash') == self.scope_hash
                        and r.get('budget_hash') == self.budget_hash and r.get('evaluator') == 'native'
                        and r.get('definition_hash') == digest(self.tasks[parent_task])
                        and r.get('status') in VALID_OUTCOMES}
            if decomposition.get('revision') != self.revision or decomposition['failure_evidence'] not in failures:
                raise ValueError('Practice must address an observed parent failure under this revision')
            if not gap.get('catalog_complete') or gap.get('matches') or not gap.get('catalog_hash'):
                raise ValueError('Complete catalog search must establish the gap')
            if not any(n['id'] == subgoal_id and n['capability'] == gap['capability'] for n in decomposition['nodes']):
                raise ValueError('Catalog gap does not match the failed subgoal')
            return {'allowed':True, 'track':'assisted_practice', 'counts_as_original_mastery':False,
                    'requirements':['Bind the missing subgoal and parent failure',
                                    'Validate scene feasibility and the subgoal checker',
                                    'Return to the unmodified parent task after practice']}
        if purpose == 'harder_challenge':
            ready = self.mastery(evidence)
            return {'allowed':ready['all_mastered'], 'track':'challenge',
                    'counts_as_original_mastery':False, 'readiness':ready}
        raise ValueError('Unknown environment change purpose')


def validate_decomposition(plan, parent_task):
    if plan.get('parent_task') != parent_task or not plan.get('failure_evidence'):
        raise ValueError('Decomposition must cite a failed parent episode')
    nodes = plan.get('nodes', [])
    if not nodes or len(nodes) > 12 or len({n['id'] for n in nodes}) != len(nodes):
        raise ValueError('Use 1..12 distinct bounded subgoals')
    pending = {n['id']:set(n.get('depends_on', [])) for n in nodes}
    for n in nodes:
        if not n.get('capability') or not n.get('postcondition') or not n.get('checker'):
            raise ValueError('Every subgoal needs a capability, observable condition and checker binding')
        if not pending[n['id']] <= set(pending):
            raise ValueError('Unknown subgoal dependency')
    while pending:
        ready = {key for key, deps in pending.items() if not deps}
        if not ready:
            raise ValueError('Subgoal dependencies must be acyclic')
        pending = {key:deps-ready for key,deps in pending.items() if key not in ready}


def resolve_practice(capability, catalog, *, catalog_complete):
    """Deterministic search of operator-indexed practice contracts.

    practice_for means an explicit subgoal contract, not fuzzy keyword similarity.
    The proposing model cannot declare a missing task by ignoring this catalog.
    A matched task still needs an applicability check for the parent's embodiment.
    """
    matches = [t['id'] for t in catalog if capability in t.get('practice_for', [])]
    if matches:
        action = 'reuse_existing_task'
    elif not catalog_complete:
        action = 'complete_catalog_search'
    else:
        action = 'create_missing_practice'
    return {'action':action, 'capability':capability, 'matches':matches,
            'catalog_hash':digest(catalog), 'catalog_complete':catalog_complete}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', required=True)
    parser.add_argument('--evidence', help='JSON array of trusted development/validation records')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--budget-hash', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--decompositions')
    parser.add_argument('--subtask-reports')
    parser.add_argument('--deferred-tasks')
    parser.add_argument('--checkers', nargs='*', default=[])
    parser.add_argument('--budget-exhausted', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(Path(args.benchmark).read_text())
    evidence = json.loads(Path(args.evidence).read_text()) if args.evidence else []
    controller = BenchmarkCurriculum(manifest['cases'], args.revision, budget_hash=args.budget_hash, checkers=args.checkers)
    def read(path, default):
        return json.loads(Path(path).read_text()) if path else default
    order = controller.next_work(evidence, decompositions=read(args.decompositions, {}),
                                 subtask_reports=read(args.subtask_reports, []),
                                 deferred_tasks=read(args.deferred_tasks, {}), budget_remaining=not args.budget_exhausted)
    order['mode'] = 'work_order_only_no_robot_or_model_execution'
    write_json(args.output, order)
    print(json.dumps({'action':order['action'], 'task_id':order['task_id'],
                      'scope_tasks':len(controller.tasks), 'new_challenges_allowed':order['new_challenge_generation_allowed']}))


if __name__ == '__main__':
    main()
