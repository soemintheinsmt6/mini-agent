import pytest

from calculator import add, average, percent, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6


def test_average():
    assert average([2, 4, 6]) == 4


def test_average_empty():
    with pytest.raises(ValueError):
        average([])


def test_percent():
    assert percent(1, 4) == 25
