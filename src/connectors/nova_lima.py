"""
Conector Nova Lima — NFS-e Nacional (adesão em 01/01/2026).
Portal antigo: https://www.novalima.mg.gov.br/ (legado)
Estratégia:
  - Todas as notas de 2026 devem usar NFS-e Nacional (chave longa).
  - Código curto (ex: 78c8f91f): fallback Playwright portal municipal.
  - CCM: prefeitura Nova Lima usa código IM interno; requer Playwright.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_nfse_nacional = NfseNacionalConnector("NOVA LIMA")


class NovaLimaConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "NOVA LIMA"

    @property
    def estrategia(self) -> str:
        return "NFS-e Nacional (2026) + portal Nova Lima fallback (Playwright)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("Nova Lima: consultando CCM para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="Portal Nova Lima não expõe CCM publicamente — requer Playwright com CNPJ",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_nova_lima_company
        return capture_nova_lima_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            return _nfse_nacional.download_invoice(row, dest_dir)
        from src.browser.playwright_runner import capture_nova_lima_invoice
        return capture_nova_lima_invoice(row, dest_dir)
