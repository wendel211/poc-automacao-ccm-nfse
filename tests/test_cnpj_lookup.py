"""Testes do enriquecimento de CNPJ com a cadeia de fallback (HTTP mockado)."""
import httpx
import respx

from src.services.cnpj_lookup import fetch_company_data

_CNPJ = "28203865000174"


@respx.mock
def test_receitaws_primeiro_sucesso():
    respx.get(f"https://receitaws.com.br/v1/cnpj/{_CNPJ}").mock(
        return_value=httpx.Response(200, json={
            "status": "OK",
            "nome": "EMPRESA TESTE LTDA",
            "situacao": "ATIVA",
            "municipio": "BELO HORIZONTE",
            "uf": "MG",
            "abertura": "01/01/2020",
            "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
            "atividade_principal": [{"text": "Atividade X"}],
        })
    )
    d = fetch_company_data(_CNPJ)
    assert d.found
    assert d.fonte == "ReceitaWS"
    assert d.razao_social == "EMPRESA TESTE LTDA"
    assert d.atividade_principal == "Atividade X"


@respx.mock
def test_fallback_para_cnpja_quando_receitaws_falha():
    respx.get(f"https://receitaws.com.br/v1/cnpj/{_CNPJ}").mock(
        return_value=httpx.Response(429)  # rate limit
    )
    respx.get(f"https://open.cnpja.com/office/{_CNPJ}").mock(
        return_value=httpx.Response(200, json={
            "company": {"name": "EMPRESA CNPJA LTDA", "nature": {"text": "LTDA"}},
            "status": {"text": "Ativa"},
            "address": {"city": "Rio de Janeiro", "state": "RJ"},
            "founded": "2019-05-05",
            "mainActivity": {"text": "Software"},
        })
    )
    d = fetch_company_data(_CNPJ)
    assert d.found
    assert d.fonte == "CNPJa"
    assert d.razao_social == "EMPRESA CNPJA LTDA"


@respx.mock
def test_fallback_para_brasilapi_quando_dois_falham():
    respx.get(f"https://receitaws.com.br/v1/cnpj/{_CNPJ}").mock(return_value=httpx.Response(500))
    respx.get(f"https://open.cnpja.com/office/{_CNPJ}").mock(return_value=httpx.Response(404))
    respx.get(f"https://brasilapi.com.br/api/cnpj/v1/{_CNPJ}").mock(
        return_value=httpx.Response(200, json={
            "razao_social": "EMPRESA BRASILAPI SA",
            "descricao_situacao_cadastral": "ATIVA",
            "municipio": "BARUERI",
            "uf": "SP",
            "cnae_fiscal_descricao": "Comércio",
        })
    )
    d = fetch_company_data(_CNPJ)
    assert d.fonte == "BrasilAPI"
    assert d.razao_social == "EMPRESA BRASILAPI SA"


@respx.mock
def test_todos_falham_retorna_erro_sem_excecao():
    respx.get(f"https://receitaws.com.br/v1/cnpj/{_CNPJ}").mock(return_value=httpx.Response(500))
    respx.get(f"https://open.cnpja.com/office/{_CNPJ}").mock(return_value=httpx.Response(500))
    respx.get(f"https://brasilapi.com.br/api/cnpj/v1/{_CNPJ}").mock(return_value=httpx.Response(500))
    d = fetch_company_data(_CNPJ)
    assert not d.found
    assert d.erro is not None


def test_cnpj_invalido():
    d = fetch_company_data("123")
    assert not d.found
    assert "inválido" in (d.erro or "")
