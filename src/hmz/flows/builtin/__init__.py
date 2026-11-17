"""The flows Humanize keeps in the package: `chat`, `ai_chan`, and the six loops everybody uses.

`chat` is one agent talking: the flow an interface opens on, and the shortest thing there is
that shows what a flow is. `ai_chan` is Ai-chan, the agent through which you operate hmz, which
the daemon runs for each conversation with her. Beside them are the loops
[FlowBench](https://humanfia.ai/projects/flowbench) scores, under the same names --
`ralph_loop`, `stateful_ralph`, `continue_loop`, `goal`, `flame_chase` and `rlar`. They are here
rather than in the [official flowverse](https://github.com/humanfia/flowverse) because they are
what Humanize is for before anything has been fetched: a machine that has never reached a
network still has to have something to open talking to and a loop to leave running, and a first
run that had to clone before it could do either would be a first run that failed on the train.

Everything else Humanize offers is in that repository, fetched when somebody asks for it: a
flow is content, and content that can change without a release is content that keeps up.

Which of the two places a flow of Humanize's is kept in is Humanize's own business, and is not
something anybody running one has to know. Both are offered under `official`, and a flow moved
from one to the other goes on answering to the name it always had.

A directory of flows and nothing else, one directory apiece: the `__init__.py` that is the
flow, whatever it imports beside it, and the `skills/` it brings. Each is written against
:mod:`hmz.flows` like any other flow and imports nothing else of Humanize's -- but `ai_chan`,
which speaks to the daemon through :mod:`hmz.sdk` -- and each declares what it asks of its
agents and runs under a budget like any other -- all but `chat` and `ai_chan`, which stop when
you do and so need no budget, `chat`, talking to whichever agent it is given, being handed
every capability of its agent's harness as well. That is the runtime's to say, in
:func:`hmz.runtime.flowing.finding.privileged`.
"""
