"""
Conector Nova Lima — NFS-e Nacional exclusivo (adesao em 01/01/2026).
Portais testados com DNS failure: novalima.nfse.com.br,
  nfse.novalima.mg.gov.br, issdigital.novalima.mg.gov.br.

Estrategia:
  - Todas as chaves longas (40+ digitos): NFS-e Nacional (captura screenshot).
  - Codigos curtos: roteados para NFS-e Nacional como primeiro tentativa;
    se rejeitar, registra como INDISPONIVEL (sistema legado desativado em 2026).
  - CCM: portal municipal offline — CCM nao disponivel publicamente.
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
        return "NFS-e Nacional exclusivo (adesao Jan/2026) — portal municipal offline"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("Nova Lima: portal municipal offline — CCM indisponivel para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="Portal Nova Lima com falha DNS — CCM nao disponivel (portal migrado para NFS-e Nacional)",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_nova_lima_company
        return capture_nova_lima_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        logger.info("Nova Lima: roteando para NFS-e Nacional (adesao Jan/2026)")
        return _nfse_nacional.download_invoice(row, dest_dir)
