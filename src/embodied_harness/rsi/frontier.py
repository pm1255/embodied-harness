"""Conservative development-only decisions; a local plateau is not an absolute limit."""
from __future__ import annotations

from dataclasses import dataclass
import math


INFRASTRUCTURE = {'infrastructure_error', 'cancelled'}
VALID_OUTCOMES = {'agent_finished', 'decision_budget_exhausted', 'control_budget_exhausted',
                  'completed', 'success', 'failed'}


def interval(successes, count):
    if not 0 <= successes <= count:
        raise ValueError('Invalid success counts')
    if not count:
        return [0.0, 1.0]
    z = 1.95996398454
    center = (successes/count + z*z/(2*count))/(1+z*z/count)
    radius = z*math.sqrt(successes/count*(1-successes/count)/count+z*z/(4*count*count))/(1+z*z/count)
    return [max(0, center-radius), min(1, center+radius)]


def paired_window(pairs, *, window_id, repair_class, look=1):
    """Fixed-window Hoeffding interval for paired binary improvement.

    Fresh, independent evaluation instances are a caller-enforced experimental
    requirement. Alpha spending over look=1,2,... controls repeated inspections
    by a union bound. This conservative interval is deliberately wide at small n.
    Infrastructure failures stay in primary success tables, but cannot certify
    stagnation. No model-written confidence scores are accepted here.
    """
    if not isinstance(look, int) or look < 1 or not pairs:
        raise ValueError('A nonempty validation window and positive look are required')
    ids, gains = [], []
    for pair in pairs:
        if pair.get('split') != 'validation':
            raise ValueError('Only independent validation may certify progress')
        ids.append(pair['instance_id'])
        for arm in ('baseline', 'candidate'):
            row = pair[arm]
            if row['status'] not in VALID_OUTCOMES or type(row['success']) is not bool:
                raise ValueError('Incomplete or infrastructure-limited pair')
        gains.append(int(pair['candidate']['success'])-int(pair['baseline']['success']))
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate validation instance')
    alpha = .05/(look*(look+1))
    mean = sum(gains)/len(gains)
    radius = math.sqrt(2*math.log(2/alpha)/len(gains))
    return {'window_id':window_id, 'repair_class':repair_class, 'split':'validation',
            'look':look, 'instance_ids':ids, 'valid_pairs':len(gains), 'gain':mean,
            'gain_lower':max(-1, mean-radius), 'gain_upper':min(1, mean+radius),
            'alpha':alpha, 'method':'paired_bounded_hoeffding_alpha_spending'}


@dataclass(frozen=True)
class FrontierPolicy:
    min_valid_trials: int = 20
    max_infrastructure_fraction: float = .2
    learned_lower_bound: float = .7
    too_hard_upper_bound: float = .2
    stalled_windows: int = 3
    minimum_meaningful_gain: float = .05

    def __post_init__(self):
        if self.min_valid_trials < 1 or self.stalled_windows < 2:
            raise ValueError('Invalid trial/window threshold')
        if not 0 <= self.max_infrastructure_fraction < 1:
            raise ValueError('Invalid infrastructure threshold')
        if not 0 <= self.too_hard_upper_bound < self.learned_lower_bound <= 1:
            raise ValueError('Invalid frontier thresholds')
        if not 0 < self.minimum_meaningful_gain <= 1:
            raise ValueError('Invalid meaningful gain')

    def assess(self, attempts, *, task_validated, repair_windows=(), budget_remaining=True):
        """Assess one task stratum, not a pool mixing different difficulty levels.

        task_validated means the scene has a positive feasibility witness and a
        independently checked success definition. A task-family name alone is
        insufficient. Thresholds are configurable engineering defaults, not laws.
        """
        if any(row.get('split') not in ('discovery', 'validation') for row in attempts):
            raise ValueError('Only development attempts may guide frontier exploration')
        infra = [r for r in attempts if r['status'] in INFRASTRUCTURE]
        valid = [r for r in attempts if r['status'] in VALID_OUTCOMES]
        unknown = len(attempts)-len(infra)-len(valid)
        if any(type(r.get('success')) is not bool for r in valid):
            raise ValueError('A final native success result must be boolean')
        diagnostic = {'attempts':len(attempts), 'valid':len(valid), 'infrastructure':len(infra),
                      'unknown':unknown, 'task_validated':task_validated,
                      'success_interval95':interval(sum(r['success'] for r in valid), len(valid))}
        def result(state, next_step):
            return {**diagnostic, 'state':state, 'next':next_step}
        if attempts and (len(infra)+unknown)/len(attempts) > self.max_infrastructure_fraction:
            return result('infrastructure_limited', 'Repair execution reliability; do not infer a capability boundary')
        if not task_validated:
            return result('task_unverified', 'Validate task semantics and a positive witness before learning from failures')
        if not attempts:
            return result('unmeasured', 'Run bounded diagnostics on reproducible development instances')
        if not budget_remaining:
            return result('budget_exhausted', 'Preserve the frontier and uncertainty; do not call the model incapable')
        if len(valid) < self.min_valid_trials:
            return result('insufficient_evidence', 'Collect more paired development trials or a diagnostic probe')
        recent = list(repair_windows)[-self.stalled_windows:]
        enough = len(recent) == self.stalled_windows
        measured = all(w.get('method') == 'paired_bounded_hoeffding_alpha_spending'
                       and w.get('split') == 'validation' and w.get('valid_pairs', 0) >= self.min_valid_trials
                       and math.isfinite(w.get('gain_upper', math.inf)) for w in recent)
        ids = [i for w in recent for i in w.get('instance_ids', [])]
        looks = [w.get('look') for w in recent]
        independent = len(ids) == len(set(ids)) and len(looks) == len(set(looks))
        diverse = len({w.get('repair_class') for w in recent}) >= 2
        if enough and measured and independent and diverse and all(
            w['gain_upper'] < self.minimum_meaningful_gain for w in recent
        ):
            return result('local_plateau', 'Archive a budget- and tool-specific boundary; decompose the task or change tool/representation class')
        low, high = diagnostic['success_interval95']
        if low >= self.learned_lower_bound:
            return result('consolidate', 'Validate transfer and old-task retention, then expand one difficulty dimension')
        if high <= self.too_hard_upper_bound:
            return result('beyond_current_frontier', 'Generate a simpler bridge task or propose a missing tool; do not repeatedly sample harder tasks')
        return result('frontier', 'Explore nearby counterexamples; test one repair hypothesis and measure paired learning progress')


def guidance_packet(task, assessment, evidence_ids):
    """A prompt-ready contract for the next proposer; no held-out evidence enters it."""
    return {'task':task, 'frontier':assessment, 'allowed_evidence':list(evidence_ids),
            'request':assessment['next'],
            'proposal_requirements':[
                'Cite a development failure and state one falsifiable repair hypothesis',
                'Identify parent task, positive anchor, and one changed difficulty dimension',
                'Choose memory, skill, tool, harness, model configuration, or task repair',
                'Predict observable outcomes and a matched-cost comparison before running',
                'Keep facts separate from hypotheses and independently validated procedures',
                'Do not modify the external evaluator, evidence ledger, or held-out partition'],
            'absorption':{'facts':'retain with episode citations even after candidate rejection',
                          'hypotheses':'retain as unverified; never assert that they improve success',
                          'procedures':'promote only after fresh transfer and old-task regression checks'}}
