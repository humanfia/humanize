"""`hmz.coganchor.spelling`: where an agent's model ends and its effort begins."""

from __future__ import annotations

import pytest

from hmz.coganchor.spelling import parted


@pytest.mark.parametrize(
    ("said", "model", "effort"),
    [
        ("claude-opus-5", "claude-opus-5", ""),
        ("claude-opus-5:high", "claude-opus-5", "high"),
        ("gpt-5:xhigh", "gpt-5", "xhigh"),
        ("model:extra-high", "model", "extra-high"),
        ("model:as configured", "model", "as configured"),
        ("model:x_high", "model", "x_high"),
        ("model:High", "model", "High"),
        ("model:swarmmax", "model", "swarmmax"),
        ("model:", "model", ""),
        ("model: ", "model", " "),
        ("", "", ""),
        # What follows the last colon is the model's own unless it is spelled as an effort.
        ("custom_provider:gateway/m", "custom_provider:gateway/m", ""),
        ("llama3:8b", "llama3:8b", ""),
        ("qwen3:latest:auto", "qwen3:latest", "auto"),
        ("qwen3:latest", "qwen3", "latest"),
        ("provider/model:7", "provider/model:7", ""),
        ("a:b-", "a:b-", ""),
    ],
)
def test_parted_splits_model_from_effort(said: str, model: str, effort: str) -> None:
    assert parted(said) == (model, effort)
