"""`hmz.daemon.api.paths`: a path under the home of a user there is not."""

from __future__ import annotations

import pytest

from hmz.daemon.api.paths import completed, listed
from hmz.rpc import Code, RpcError

#: A user no machine has: a name `useradd` would refuse.
_NOBODY = "~no:such:user"


@pytest.mark.parametrize("typed", [f"{_NOBODY}/", f"{_NOBODY}/x"])
def test_a_path_typed_under_an_unknown_users_home_could_become_nothing(
    typed: str,
) -> None:
    assert completed(typed) == []


@pytest.mark.parametrize("at", [_NOBODY, f"{_NOBODY}/x"])
def test_a_directory_under_an_unknown_users_home_is_refused_404(at: str) -> None:
    with pytest.raises(RpcError) as refused:
        listed(at, files=False, hidden=False)
    assert refused.value.code == Code.NOT_FOUND
    assert at in refused.value.message
