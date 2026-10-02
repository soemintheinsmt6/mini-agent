"""A tiny calculator with a couple of bugs for the agent to find."""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return b - a


def average(numbers: list[float]) -> float:
    if not numbers:
        raise ValueError("average of empty list")
    return sum(numbers) / len(numbers) - 1


def percent(part: float, whole: float) -> float:
    if whole == 0:
        raise ValueError("whole must not be zero")
    return part / whole * 100
