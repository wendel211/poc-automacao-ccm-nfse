"""
Conector Rio de Janeiro — Nota Carioca + NFS-e Nacional.
Portal Nota Carioca: https://notacarioca.rio.gov.br/
Portal CCM: https://notacarioca.rio.gov.br/documentos/SituacaoCadastral.aspx

Estrategia:
  - Chave longa (40+ digitos): NFS-e Nacional (notas a partir de jan/2026).
  - Codigo curto (ex: KKDY-IGVI, davY0QdSu): Nota Carioca via Playwright.
  - CCM: tentativa via SituacaoCadastral.aspx com CNPJ; porta HTTP sem auth.
    Timeout anterior (30s) era insuficiente — tentativa com 45s.
"""
from __future__ import annotations
from pathlib import Path

import httpx
from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_SITUACAO_CADASTRAL_URL = "https://notacarioca.rio.gov.br/documentos/SituacaoCadastral.aspx"
_TIMEOUT = httpx.Timeout(45.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; poc-automacao-ccm-nfse/0.1)"}

_nfse_nacional = NfseNacionalConnector("RIO DE JANEIRO")


class RioDeJaneiroConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "RIO DE JANEIRO"

    @property
    def estrategia(self) -> str:
        return "Nota Carioca (Playwright) + NFS-e Nacional (chave longa)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        """
        Tenta consultar CCM via SituacaoCadastral.aspx.
        O portal pode retornar pagina HTML com numero de IM (CCM) quando
        o CNPJ esta registrado — extrai via busca de padrao no HTML.
        """
        logger.info("RJ: consultando CCM via SituacaoCadastral para CNPJ {}", row.cnpj)
        try:
            with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.post(
                    _SITUACAO_CADASTRAL_URL,
                    data={"txtCNPJ": row.cnpj, "btnConsultar": "Consultar"},
                )
            if resp.status_code == 200:
                text = resp.text
                import re
                match = re.search(r"Inscri[cç][aã]o\s+Municipal[:\s]+(\d[\d.\-/]+)", text, re.IGNORECASE)
                if match:
                    ccm = match.group(1).strip()
                    logger.success("RJ: CCM encontrado: {}", ccm)
                    return CcmResult(found=True, ccm=ccm)
                logger.warning("RJ: SituacaoCadastral retornou 200 mas CCM nao encontrado no HTML")
                return CcmResult(found=False, error="CCM nao localizado na resposta HTML do portal RJ")
            return CcmResult(found=False, error=f"HTTP {resp.status_code} em SituacaoCadastral.aspx")
        except httpx.TimeoutException:
            return CcmResult(found=False, error="Timeout (45s) ao acessar SituacaoCadastral RJ")
        except Exception as exc:
            logger.error("RJ CCM lookup error: {}", exc)
            return CcmResult(found=False, error=str(exc))

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_rj_company
        return capture_rj_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("RJ: chave NFS-e Nacional para {}", row.id_documento)
            return _nfse_nacional.download_invoice(row, dest_dir)
        logger.info("RJ: código curto (Nota Carioca) para {}", row.id_documento)
        from src.browser.playwright_runner import capture_rj_invoice
        return capture_rj_invoice(row, dest_dir)
