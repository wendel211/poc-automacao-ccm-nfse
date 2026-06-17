"""
Conector Belo Horizonte — Portal NFS-e BH (servicos.pbh.gov.br).
URL verificada: https://servicos.pbh.gov.br/nfse/autenticidade (HTTP 200).
URL antiga bhiss.pbh.gov.br não resolve DNS.

Estratégia:
  - Chave longa (40+ dígitos): NfseNacionalConnector.
  - Código curto (ex: 1f3be52b, YVSC-ARGB): Playwright via portal BH.
  - CCM: portal BH usa Sydle SPA (Web Components), não renderiza form
    em headless sem tempo de espera elevado — captura screenshot como evidência.
"""
from __future__ import annotations
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_BH_AUTENTICIDADE = "https://servicos.pbh.gov.br/nfse/autenticidade"
_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; poc-automacao-ccm-nfse/0.1)"}

_nfse_nacional = NfseNacionalConnector("BELO HORIZONTE")


class BeloHorizonteConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "BELO HORIZONTE"

    @property
    def estrategia(self) -> str:
        return "BHISS Digital (Playwright) + NFS-e Nacional fallback"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("BH: consultando CCM para CNPJ {}", row.cnpj)
        try:
            with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.get(_BH_AUTENTICIDADE)
            if resp.status_code in (200, 302):
                return CcmResult(
                    found=False,
                    error="Portal BH (servicos.pbh.gov.br) requer sessão para consulta de CCM",
                )
            return CcmResult(found=False, error=f"HTTP {resp.status_code}")
        except httpx.TimeoutException:
            return CcmResult(found=False, error="Timeout ao acessar BHISS Digital")
        except Exception as exc:
            return CcmResult(found=False, error=str(exc))

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_bh_company
        return capture_bh_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("BH: chave NFS-e Nacional detectada para {}", row.id_documento)
            return _nfse_nacional.download_invoice(row, dest_dir)
        from src.browser.playwright_runner import capture_bh_invoice
        return capture_bh_invoice(row, dest_dir)
