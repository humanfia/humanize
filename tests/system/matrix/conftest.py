"""The fixtures the regression matrix's cells name, re-exported from where they are written.

`cell` and `billed` are `tests/matrix/fixtures.py`'s: a CLI at its place for a row of every
CLI, and the prices and the bill for a row run once. `ssh_box` and `docker_box` are
`tests/flows/sshd.py`'s: another machine, an sshd in a container, for the rows that run an
agent's turn over ssh; and another machine with a docker daemon of its own, for the row that
puts an agent's container on a daemon elsewhere. `daemon` is `tests/machines/fixtures.py`'s:
docker here, holding the image a container of the rows that start one is started from.
The hooks that label each cell and draw the grid are in `tests/conftest.py`: a hook here would
fire on the workers that run the cells and never on the process that draws the summary.
"""

from __future__ import annotations

from tests.flows.sshd import docker_box, ssh_box
from tests.machines.fixtures import daemon
from tests.matrix.fixtures import billed, cell

__all__ = ["billed", "cell", "daemon", "docker_box", "ssh_box"]
