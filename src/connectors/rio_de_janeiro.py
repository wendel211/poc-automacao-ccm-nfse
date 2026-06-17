"""
Conector Rio de Janeiro — NFS-e Nacional (notas de 2026) + Nota Carioca (legado).
Portal Nota Carioca: https://notacarioca.rio.gov.br/
Estratégia:
  - Chave longa (50+ dígitos): NFS-e Nacional (notas a partir de jan/2026).
  - Código curto (ex: KKDY-IGVI, davY0QdSu): Nota Carioca via Playwright.
  - CCM (Inscrição Municipal RJ): consultar via SMFP digital se disponível.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_nfse_nacional = NfseNacionalConnector("RIO DE JANEIRO")


class RioDeJaneiroConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "RIO DE JANEIRO"

    @property
    def estrategia(self) -> str:
        return "NFS-e Nacional (2026) + Nota Carioca fallback (Playwright)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("RJ: consultando CCM para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="SMFP RJ requer autenticação para CCM — automação com login necessária",
        )

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
