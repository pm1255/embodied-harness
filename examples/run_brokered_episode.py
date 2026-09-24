"""Robot-side episode; no GPT API credentials are required on this machine."""
import argparse
import json
from pathlib import Path

from embodied_harness.adapters import create_environment
from embodied_harness.broker import DirectoryPlanner
from embodied_harness.runner import run_episode
from embodied_harness.trace import Trace
from embodied_harness.vla import configured_policy

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--config', required=True)
p.add_argument('--out', required=True)
p.add_argument('--broker', required=True)
p.add_argument('--task', required=True)
a = p.parse_args()
root = Path(a.out)
run_episode(create_environment('robotwin', root/'camera', json.loads(Path(a.config).read_text())),
            DirectoryPlanner(a.broker, 'gpt-6-sol'), Trace(root), a.task, seed=0,
            max_decisions=8, max_control_ticks=600, tools_factory=configured_policy)
