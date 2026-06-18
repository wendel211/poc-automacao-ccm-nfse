"""
Cliente da API SEFIN Nacional (NFS-e Nacional) com autenticação por certificado
digital ICP-Brasil (mTLS) — a forma OFICIAL de buscar a NFS-e Federal por chave.

Os portais públicos da NFS-e Nacional bloqueiam scraping:
  - `/consultapublica`        -> protegido por hCaptcha (sitekey verificado)
  - `/EmissorNacional/...`    -> exige login gov.br
  - `/Visualizar?chaveAcesso` -> HTTP 500 sem sessão autenticada

O canal programático sancionado é a API SEFIN/ADN Nacional, que responde
`496 SSL certificate required` para requisições sem certificado de cliente —
ou seja, exige mTLS com um certificado ICP-Brasil (e-CNPJ A1, por exemplo).

Este cliente implementa esse caminho de verdade. Quando um certificado é
configurado (variáveis de ambiente abaixo), ele baixa o XML/DANFSe real da nota.
Sem certificado, retorna uma mensagem clara — o POC não tem o e-CNPJ da empresa,
mas o código está pronto para produção.

Configuração (variáveis de ambiente):
  NFSE_CERT_PEM   caminho do certificado de cliente em PEM
  NFSE_KEY_PEM    caminho da chave privada em PEM
  NFSE_KEY_SENHA  (opcional) senha da chave privada

Conversão do e-CNPJ A1 (.pfx) para PEM:
  openssl pkcs12 -in ecnpj.pfx -clcerts -nokeys -out cert.pem
  openssl pkcs12 -in ecnpj.pfx -nocerts -nodes  -out key.pem
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

# Endpoint ADN/SEFIN Nacional — exige mTLS (responde 496 sem certificado)
_NFSE_XML_URL = "https://adn.nfse.gov.br/contribuinteisn/nfse/{chave}"
_DANFSE_URL = "https://sefin.nfse.gov.br/sefinnacional/danfse/{chave}"
_TIMEOUT = httpx.Timeout(30.0)


@dataclass
class SefinResult:
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None
    cert_configured: bool = False


def _cert_from_env() -> Optional[tuple[str, str] | tuple[str, str, str]]:
    cert = os.getenv("NFSE_CERT_PEM")
    key = os.getenv("NFSE_KEY_PEM")
    senha = os.getenv("NFSE_KEY_SENHA")
    if not cert or not key:
        return None
    if not Path(cert).exists() or not Path(key).exists():
        logger.warning("SEFIN: NFSE_CERT_PEM/NFSE_KEY_PEM configurados mas arquivos não encontrados")
        return None
    return (cert, key, senha) if senha else (cert, key)


def fetch_nfse(chave: str, dest_dir: Path) -> SefinResult:
    """
    Baixa o XML da NFS-e Nacional pela API SEFIN/ADN usando mTLS.

    Retorna SefinResult. Nunca levanta exceção — falhas viram `error` para o
    pipeline registrar a tentativa sem abortar.
    """
    cert = _cert_from_env()
    if cert is None:
        return SefinResult(
            success=False,
            cert_configured=False,
            error=(
                "API SEFIN Nacional exige certificado ICP-Brasil (mTLS). "
                "Configure NFSE_CERT_PEM e NFSE_KEY_PEM para baixar o XML/DANFSe real."
            ),
        )

    chave = "".join(ch for ch in chave if ch.isdigit())
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = _NFSE_XML_URL.format(chave=chave)

    try:
        with httpx.Client(cert=cert, timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"Accept": "application/xml"})
        if resp.status_code == 200 and resp.content:
            out = dest_dir / f"nfse_{chave[:20]}.xml"
            out.write_bytes(resp.content)
            logger.success("SEFIN: XML da NFS-e baixado para chave {}...", chave[:12])
            return SefinResult(success=True, file_path=str(out), cert_configured=True)
        return SefinResult(
            success=False,
            cert_configured=True,
            error=f"SEFIN Nacional retornou HTTP {resp.status_code} (verifique o certificado / a chave)",
        )
    except Exception as exc:  # noqa: BLE001 — registra tentativa sem abortar pipeline
        logger.error("SEFIN: erro ao baixar NFS-e: {}", exc)
        return SefinResult(success=False, cert_configured=True, error=str(exc))


def cert_disponivel() -> bool:
    """True se há certificado ICP-Brasil configurado e válido no ambiente."""
    return _cert_from_env() is not None
