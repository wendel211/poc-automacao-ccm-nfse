"""
Enriquecimento de dados cadastrais da empresa a partir do CNPJ.

A Inscrição Municipal (CCM) não é exposta por nenhuma fonte pública federal —
é um cadastro de cada prefeitura, acessível apenas com autenticação no portal
municipal. Para entregar dados reais mesmo assim, este serviço consulta o
cadastro federal da Receita (razão social, situação, endereço, atividade,
natureza jurídica), que constitui o cadastro oficial da empresa.

Usa uma cadeia de fallback entre provedores públicos para resiliência a
rate-limit e instabilidade:

    ReceitaWS  ->  CNPJa (open)  ->  BrasilAPI

A primeira resposta válida vence. Resultados são normalizados para o modelo
CompanyData independente do provedor de origem.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from loguru import logger

_TIMEOUT = httpx.Timeout(25.0)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass
class CompanyData:
    cnpj: str
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    situacao_cadastral: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    data_abertura: Optional[str] = None
    natureza_juridica: Optional[str] = None
    atividade_principal: Optional[str] = None
    fonte: Optional[str] = None
    erro: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.razao_social is not None


def _norm(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


# --------------------------------------------------------------------------- #
# Provedores — cada um devolve CompanyData ou levanta exceção.
# --------------------------------------------------------------------------- #

def _from_receitaws(cnpj: str, client: httpx.Client) -> Optional[CompanyData]:
    r = client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj}")
    if r.status_code != 200:
        raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
    d = r.json()
    if d.get("status") == "ERROR":
        raise ValueError(d.get("message", "ReceitaWS retornou erro"))
    atividades = d.get("atividade_principal") or []
    return CompanyData(
        cnpj=cnpj,
        razao_social=d.get("nome"),
        nome_fantasia=d.get("fantasia") or None,
        situacao_cadastral=d.get("situacao"),
        municipio=d.get("municipio"),
        uf=d.get("uf"),
        data_abertura=d.get("abertura"),
        natureza_juridica=d.get("natureza_juridica"),
        atividade_principal=(atividades[0].get("text") if atividades else None),
        fonte="ReceitaWS",
    )


def _from_cnpja(cnpj: str, client: httpx.Client) -> Optional[CompanyData]:
    r = client.get(f"https://open.cnpja.com/office/{cnpj}")
    if r.status_code != 200:
        raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
    d = r.json()
    company = d.get("company") or {}
    address = d.get("address") or {}
    return CompanyData(
        cnpj=cnpj,
        razao_social=company.get("name"),
        nome_fantasia=d.get("alias") or None,
        situacao_cadastral=(d.get("status") or {}).get("text"),
        municipio=address.get("city"),
        uf=address.get("state"),
        data_abertura=d.get("founded"),
        natureza_juridica=(company.get("nature") or {}).get("text"),
        atividade_principal=(d.get("mainActivity") or {}).get("text"),
        fonte="CNPJa",
    )


def _from_brasilapi(cnpj: str, client: httpx.Client) -> Optional[CompanyData]:
    r = client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
    if r.status_code != 200:
        raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
    d = r.json()
    return CompanyData(
        cnpj=cnpj,
        razao_social=d.get("razao_social"),
        nome_fantasia=d.get("nome_fantasia") or None,
        situacao_cadastral=d.get("descricao_situacao_cadastral"),
        municipio=d.get("municipio"),
        uf=d.get("uf"),
        data_abertura=d.get("data_inicio_atividade"),
        natureza_juridica=d.get("natureza_juridica"),
        atividade_principal=d.get("cnae_fiscal_descricao"),
        fonte="BrasilAPI",
    )


_PROVIDERS = (
    ("ReceitaWS", _from_receitaws),
    ("CNPJa", _from_cnpja),
    ("BrasilAPI", _from_brasilapi),
)


def fetch_company_data(cnpj_raw: str) -> CompanyData:
    """
    Consulta os provedores em cadeia até obter um cadastro válido.
    Nunca levanta exceção — devolve CompanyData com `erro` preenchido se todos
    falharem, para o pipeline registrar a tentativa sem abortar.
    """
    cnpj = _norm(cnpj_raw)
    if len(cnpj) != 14:
        return CompanyData(cnpj=cnpj, erro=f"CNPJ inválido: {cnpj_raw!r}")

    erros: list[str] = []
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        for nome, provider in _PROVIDERS:
            try:
                data = provider(cnpj, client)
                if data and data.found:
                    logger.success("CNPJ {} enriquecido via {}: {}", cnpj, nome, data.razao_social)
                    return data
                erros.append(f"{nome}: sem dados")
            except Exception as exc:  # noqa: BLE001 — fallback resiliente por design
                logger.warning("CNPJ {} via {} falhou: {}", cnpj, nome, exc)
                erros.append(f"{nome}: {str(exc)[:60]}")

    return CompanyData(cnpj=cnpj, erro="; ".join(erros) or "Nenhum provedor retornou dados")
