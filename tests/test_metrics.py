from metrics import safe_float


def test_safe_float_none():
    assert safe_float(None) == 0.0
    assert safe_float(None, 1.0) == 1.0


def test_safe_float_number():
    assert safe_float(42) == 42.0
    assert safe_float(3.14) == 3.14


def test_safe_float_value_dict():
    assert safe_float({"Value": 100}) == 100.0
    assert safe_float({"Value": 2.5}) == 2.5
