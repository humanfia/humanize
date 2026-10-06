from collections.abc import Callable

import pytest

from stats import mean, median, mode


def test_mean() -> None:
    assert mean([1, 2, 3, 4]) == 2.5


@pytest.mark.parametrize(("values", "expected"), [([3, 1, 2], 2), ([4, 1, 3, 2], 2.5), ([7], 7)])
def test_median(values: list[float], expected: float) -> None:
    assert median(values) == expected


@pytest.mark.parametrize(("values", "expected"), [([1, 2, 2, 3], 2), ([3, 1, 3, 1], 1)])
def test_mode(values: list[float], expected: float) -> None:
    assert mode(values) == expected


@pytest.mark.parametrize("function", [mean, median, mode])
def test_empty(function: Callable[[list[float]], float]) -> None:
    with pytest.raises(ValueError):
        function([])
