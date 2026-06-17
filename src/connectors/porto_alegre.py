"""
Conector Porto Alegre — NFS-e Porto Alegre / NFS-e Nacional.
Portal: https://nfse.portoalegre.rs.gov.br/
Estratégia:
  - Chave longa: NFS-e Nacional.
  - Código curto (ex: b46a80ef): portal municipal via Playwright.
  - CCM (CMEI): portal municipal SMAM/SMF de Porto Alegre.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_nfse_nacional = NfseNacionalConnector("PORTO ALEGRE")


class PortoAlegreConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "PORTO ALEGRE"

    @property
    def estrategia(self) -> str:
        return "NFS-e Nacional (chave longa) + portal municipal POA (Playwright)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("POA: consultando CCM para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="Portal Porto Alegre requer login para consulta de CCM/IM",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_poa_company
        return capture_poa_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            return _nfse_nacional.download_invoice(row, dest_dir)
        from src.browser.playwright_runner import capture_poa_invoice
        return capture_poa_invoice(row, dest_dir)
