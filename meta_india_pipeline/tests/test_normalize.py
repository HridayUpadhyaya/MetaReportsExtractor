from app.services.normalize import parse_number, parse_rate, normalize_category

def test_numbers():
    assert parse_number("25.6 M") == 25_600_000
    assert parse_number("123.4 K") == 123_400

def test_rates():
    assert parse_rate("99.6%") == 0.996
    assert parse_rate("0.996") == 0.996

def test_category():
    assert "Terrorism" in normalize_category("Dangerous Organisations and Individuals: Terrorist Propaganda")
