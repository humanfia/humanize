"""The fixtures the regression matrix's cells name, re-exported from where they are written.

`cell` is `tests/matrix/fixtures.py`'s, and `ssh_box` is `tests/flows/sshd.py`'s: another
machine, an sshd in a container, for the row that runs an agent's turn over ssh.
The hooks that label each cell and draw the grid are in `tests/conftest.py`: a hook here would
fire on the workers that run the cells and never on the process that draws the summary.
"""

from __future__ import annotations

from tests.flows.sshd import ssh_box
from tests.matrix.fixtures import cell

__all__ = ["cell", "ssh_box"]
