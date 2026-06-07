# tests/biocanvas/test_sample.py

from biocanvas.sample import add_numbers


def test_add_numbers_success():
    """Verify core arithmetic maps correctly."""

    assert add_numbers(2, 3) == 5
