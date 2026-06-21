import re


def normalize(cnpj: str) -> str:
    """Remove máscara e retorna 14 dígitos."""
    digits = re.sub(r"\D", "", cnpj or "")
    if len(digits) != 14:
        raise ValueError(f"CNPJ inválido: {cnpj!r}")
    return digits


def format_masked(cnpj: str) -> str:
    d = normalize(cnpj)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def is_nfse_nacional_key(cod: str) -> bool:
    """Chave NFS-e Nacional: 50 digitos numericos."""
    digits = re.sub(r"\s", "", cod or "")
    return bool(re.fullmatch(r"\d{50}", digits))
