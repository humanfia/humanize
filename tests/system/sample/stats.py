"""A tiny statistics library."""


def mean(values: list[float]) -> float:
    """The arithmetic mean of `values`; raises ValueError when empty."""
    if not values:
        raise ValueError("mean of nothing")
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    """The median of `values`; raises ValueError when empty."""
    raise NotImplementedError


def mode(values: list[float]) -> float:
    """The most common value of `values`, the smallest on a tie; raises ValueError when empty."""
    raise NotImplementedError
