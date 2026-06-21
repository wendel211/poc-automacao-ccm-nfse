import pytest
from src.utils.cnpj import normalize, format_masked, is_nfse_nacional_key


def test_normalize_masked():
    assert normalize("28.203.865/0001-74") == "28203865000174"


def test_normalize_digits_only():
    assert normalize("28203865000174") == "28203865000174"


def test_normalize_invalid():
    with pytest.raises(ValueError):
        normalize("123")


def test_format_masked():
    assert format_masked("28203865000174") == "28.203.865/0001-74"


def test_nfse_nacional_key_long():
    # Chave NFS-e Nacional: 50 digitos.
    key = "31062002228203865000174000000000002426013942565090"
    assert is_nfse_nacional_key(key) is True


def test_nfse_nacional_key_short():
    assert is_nfse_nacional_key("YVSC-ARGB") is False
    assert is_nfse_nacional_key("1f3be52b") is False


def test_nfe_44_digits_is_not_nfse_nacional_even_with_spaces():
    # Chave NF-e agrupada com espacos, como aparece na planilha.
    key = "3126 0207 2211 0200 0186 5500 1000 0045 8015 9362 3410"
    assert is_nfse_nacional_key(key) is False
