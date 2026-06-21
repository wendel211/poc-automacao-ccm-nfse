from src.services import captcha_solver


def test_placeholder_2captcha_key_is_ignored(monkeypatch):
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "SUA_CHAVE_2CAPTCHA")

    assert captcha_solver._valid_api_key() is None


def test_realistic_2captcha_key_is_accepted(monkeypatch):
    fake_key = "0123456789abcdef0123456789abcdef"
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", fake_key)

    assert captcha_solver._valid_api_key() == fake_key
