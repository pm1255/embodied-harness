"""Version proposals for mutable agent components, without executing generated code.

The evaluation runner is an external trust boundary. Staging a Python artifact is
not installing or sandboxing it. A production runner must isolate candidate code
from credentials, the evaluator, stored evidence, and hidden test definitions.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from .core import digest


COMPONENTS = {'model_config', 'harness', 'memory', 'skills', 'tools', 'tasks'}


class CandidateArchive:
    def __init__(self, store):
        self.store = store

    def propose(self, *, parent, changes, hypothesis, evidence, actor='experiment_brain'):
        """Archive a branch, including rejected tool/source-code proposals.

        changes maps component/path to UTF-8 source or JSON text. No repository
        file is overwritten and no generated import/eval/exec is performed.
        """
        rows = self.store.verify()
        known = {r['event_id'] for r in rows}
        if parent != 'baseline' and not any(r['event_id'] == parent and r['kind'] == 'change_proposed' for r in rows):
            raise ValueError('Unknown parent revision')
        if not evidence or any(e not in known for e in evidence):
            raise ValueError('Proposals require existing evidence')
        for row in rows:
            if row['event_id'] in evidence:
                if row['payload'].get('split') == 'heldout':
                    raise ValueError('Held-out evidence cannot guide a proposal')
                if row['kind'] != 'rollout' or row['payload'].get('split') not in ('discovery', 'validation'):
                    raise ValueError('Cite actual development rollout evidence')
        if not changes or not hypothesis.strip():
            raise ValueError('A concrete change and repair hypothesis are required')
        artifacts = {}
        for name, content in changes.items():
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or len(path.parts) < 2
                    or path.parts[0] not in COMPONENTS or str(path) != name
                    or '\\' in name):
                raise ValueError('Change must belong to a mutable component')
            if not isinstance(content, str) or len(content.encode()) > 1_000_000:
                raise ValueError('Artifact must be bounded UTF-8 text')
            artifacts[name] = self.store.put(content.encode(), 'text/plain')
        proposal = {'parent':parent, 'hypothesis':hypothesis, 'evidence':evidence,
                    'components':sorted({name.split('/')[0] for name in changes}),
                    'execution_status':'staged_not_executed'}
        identity = 'candidate/'+digest({'proposal':proposal, 'artifacts':artifacts})
        return self.store.record(identity, 'change_proposed', actor, proposal, artifacts)

    def record_evaluation(self, candidate_id, report):
        """Called by the external evaluator, never by the proposing model.

        This is an artifact/state contract, not a statistical test or an access
        control service. The runner is responsible for producing true reports.
        Missing transfer/retention/budget checks fail closed.
        """
        rows = self.store.verify()
        if not any(r['event_id'] == candidate_id and r['kind'] == 'change_proposed' for r in rows):
            raise ValueError('Unknown candidate')
        if report.get('split') != 'validation' or report.get('candidate_id') != candidate_id:
            raise ValueError('Evaluation must bind the exact candidate and validation split')
        required = ('contract_passed', 'transfer_passed', 'retention_passed',
                    'budget_passed', 'independent_evaluator', 'evidence_verified')
        accepted = all(report.get(key) is True for key in required)
        artifact = self.store.put(json.dumps(report, sort_keys=True, allow_nan=False).encode())
        return self.store.record('evaluation/'+digest(report), 'candidate_evaluated', 'experiment_evaluator',
                                 {'candidate':candidate_id, 'accepted':accepted,
                                  'failed_checks':[key for key in required if report.get(key) is not True]},
                                 {'report':artifact})

    def activate(self, evaluation_id):
        rows = self.store.verify()
        evaluation = next((r for r in rows if r['event_id'] == evaluation_id), None)
        if not evaluation or evaluation['kind'] != 'candidate_evaluated' or not evaluation['payload']['accepted']:
            raise ValueError('Only an externally validated candidate can be activated')
        current = self.active_revision()
        target = evaluation['payload']['candidate']
        if current == target:
            return current
        self.store.record(f'activation/{len(rows)}', 'revision_activated', 'experiment_evaluator',
                          {'previous':current, 'target':target, 'evaluation':evaluation_id})
        return target

    def rollback(self, target, reason):
        rows = self.store.verify()
        approved = {'baseline'} | {r['payload']['target'] for r in rows if r['kind'] == 'revision_activated'}
        if target not in approved or not reason.strip():
            raise ValueError('Rollback requires a previously active revision and reason')
        return self.store.record(f'rollback/{len(rows)}', 'revision_rolled_back', 'experiment_evaluator',
                                 {'previous':self.active_revision(), 'target':target, 'reason':reason})

    def active_revision(self):
        revisions = [r for r in self.store.verify() if r['kind'] in ('revision_activated', 'revision_rolled_back')]
        return revisions[-1]['payload']['target'] if revisions else 'baseline'
