"""The fixtures the regression matrix's cells name, re-exported from where they are written.

`cell` is `tests/matrix/fixtures.py`'s, and `ssh_box` and `docker_box` are
`tests/flows/sshd.py`'s: another machine, an sshd in a container, for the rows that run an
agent's turn over ssh; and another machine with a docker daemon of its own, for the row that
puts an agent's container on a daemon elsewhere.
The hooks that label each cell and draw the grid are in `tests/conftest.py`: a hook here would
fire on the workers that run the cells and never on the process that draws the summary.
"""

from __future__ import annotations

from tests.flows.sshd import docker_box, ssh_box
from tests.matrix.fixtures import cell

__all__ = ["cell", "docker_box", "ssh_box"]
