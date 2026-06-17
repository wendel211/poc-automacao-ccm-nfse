"""
Conector Porto Alegre — NFS-e Nacional (portal municipal fora do ar).
Portais testados com DNS failure: nfse.portoalegre.rs.gov.br,
  portalnfse.portoalegre.rs.gov.br, nfse.pmpa.com.br.

Estrategia:
  - Chave longa (40+ digitos): NFS-e Nacional (captura screenshot).
  - Codigo curto (ex: b46a80ef): portal municipal indisponivel — registra como
    INDISPONIVEL; documento nao pode ser obtido sem acesso ao sistema legado.
  - CCM: portal municipal offline — CCM nao disponivel publicamente.
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
        return "NFS-e Nacional (chave longa) | portal municipal POA offline (codigo curto = INDISPONIVEL)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("POA: portal municipal com falha DNS — CCM indisponivel para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="Portal Porto Alegre com falha DNS — CCM nao disponivel",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_poa_company
        return capture_poa_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("POA: chave NFS-e Nacional — delegando para NfseNacionalConnector")
            return _nfse_nacional.download_invoice(row, dest_dir)
        logger.warning("POA: codigo curto {} — portal municipal offline", row.cod_verificacao)
        return DownloadResult(
            success=False,
            error="Portal Porto Alegre com falha DNS — documento indisponivel para codigo curto",
        )
