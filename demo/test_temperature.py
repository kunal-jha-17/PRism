from demo.temperature import to_celsius, to_fahrenheit


def test_to_celsius_freezing():
    assert to_celsius(32) == 0


def test_to_fahrenheit_offset():
    assert to_fahrenheit(0) == 32
    assert to_fahrenheit(100) == 212
