# Adding tools and learned policies

A tool is a typed schema plus a cooperative executor. The operator installs plugins; model text cannot name a Python module or execute arbitrary code.

```python
from embodied_harness.runtime import Tool
from embodied_harness.protocol import ToolResult
from embodied_harness.tools import object_schema

def register(env, registry):
    def hold(args, ctx):
        target = env.ee_position()
        for _ in range(10):
            env.servo(target, 'open')
            yield {'actual_m': env.ee_position(), 'target_m': target}
        return ToolResult('succeeded', {'meaning': 'hold command completed'})

    registry.add(Tool('hold_open', 'Hold position with gripper open for ten ticks.',
                      object_schema({}), hold, max_ticks=11))
```

Save this as `my_tools.py` on Python's import path and pass `--tools-factory my_tools:register` to `run`. Plugin schemas must be compatible with strict OpenAI function calling: closed objects and explicitly required fields. Validate with a request-contract test before using an API account.

For a VLA, the plugin should call a locally configured policy service, validate its action representation, and execute a bounded action chunk through a compatible adapter. Count policy inferences and record model/checkpoint identity in separate trace events. Do not silently add API or GPU work while advertising reduced model calls. An action-chunk length is not a guarantee of task completion.

For a grasp skill, register the tool only when perception, grasp pose generation, motion execution and result verification exist. Report `unknown` evidence by failing back to a model decision rather than declaring success. A skill can use observed sensor facts as preconditions. Do not read simulator object state or task predicates in a sensor-only skill.

There is no built-in generic VLA or MoveIt connector in v0.1. The extension example is executable, while those integrations are future work. Native blocking libraries must enforce stop/deadline behavior at their own layer.
