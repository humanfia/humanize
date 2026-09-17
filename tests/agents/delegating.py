"""A flow's own callback, offered to a coding agent as a tool it may reach for.

`tests/{integration,system}/agents/test_tools.py` are two halves of one subject. The first
drives the whole road against things this repo wrote -- the protocol answered a message at a
time, the socket a toolbox serves on, a client script standing in for a CLI -- and the second
starts a real `claude` to find out whether the `--mcp-config` humanize writes is a shape Claude
still agrees with.

What both need is a tool to offer, and it has to be the *same* tool: the schema below is what
the integration half asserts humanize serves and what the real CLI in the system half has to
read and list. Two copies would be a schema corrected in the half that is run by CI and left
alone in the half that is the only one able to say a CLI still accepts it.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from -- and because the two halves are no longer under
one directory to put a conftest in.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from hmz.coganchor.agents import Tool


class Asked(BaseModel):
    """What the tool under test is called with."""

    task: str = Field(description="what to have it do")
    times: int = 1


def delegate(seen: list[Asked]) -> Tool:
    """A callback that writes down what it was called with and answers.

    Args:
      seen: Where each call is appended, so a test can read what arrived.

    Returns:
      The tool, under the name both halves look for it by.
    """

    def called(said: Asked) -> str:
        seen.append(said)
        return f"did {said.task} {said.times}x"

    return Tool(
        name="delegate",
        about="hand a task to another flow and wait for what it comes to",
        takes=Asked,
        call=called,
    )
