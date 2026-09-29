"""fence -- holding an agent CLI to the scopes a flow's `Permission` grants it.

A CLI that can be told what it may reach is told natively. Where one cannot, the fence is
put around it from outside, and for the network that fence has exactly one gate:
:class:`Proxy`, which passes a connection only to the hosts the backend cannot run without.
"""

from __future__ import annotations

from hmz.coganchor.fence.proxy import Proxy, permits

__all__ = ["Proxy", "permits"]
