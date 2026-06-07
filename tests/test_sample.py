# tests/test_sample.py

def add_numbers(a: int, b: int) -> int:
    return a + b

def test_add_numbers_success():
    """Verify core arithmetic maps correctly."""
    assert add_numbers(2, 3) == 5