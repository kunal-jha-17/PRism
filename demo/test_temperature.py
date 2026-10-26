from demo.temperature import to_celsius


def test_to_celsius_freezing():
    assert to_celsius(32) == 0
