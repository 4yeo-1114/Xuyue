# -*- coding: utf-8 -*-
from app.services.ai_chat_math_style import normalize_chat_math_text


def test_dollar_wrapped_units():
    raw = "强化单位量感：$cm^3, dm^3, m^3, L, mL$ 的实际大小"
    out = normalize_chat_math_text(raw)
    assert "$" not in out
    assert "^3" not in out
    assert "cm³" in out
    assert "dm³" in out
    assert "m³" in out


def test_bare_unit_power():
    assert "cm³" in normalize_chat_math_text("体积 cm^3 与 dm^3")


if __name__ == "__main__":
    test_dollar_wrapped_units()
    test_bare_unit_power()
    print("ok")
