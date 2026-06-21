"""Rio de Janeiro connector: Certec cadastro + Nota Carioca/NFS-e Nacional."""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.services.rj_certec import consultar_cadastro_rj
from src.utils.cnpj import is_nfse_nacional_key

_nfse_nacional = NfseNacionalConnector("RIO DE JANEIRO")


class RioDeJaneiroConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "RIO DE JANEIRO"

    @property
    def estrategia(self) -> str:
        return "Certec RJ cadastral + Nota Carioca/NFS-e Nacional"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("RJ: consultando CCM via Certec para CNPJ {}", row.cnpj)
        result = consultar_cadastro_rj(row.cnpj)
        return CcmResult(found=result.success, ccm=result.inscricao, error=result.error)

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        cached = dest_dir / f"cadastro_municipal_rj_certec_{row.cnpj}.pdf"
        if cached.exists() and cached.stat().st_size > 1000:
            logger.info("RJ: reutilizando comprovante Certec ja baixado para CNPJ {}", row.cnpj)
            return DownloadResult(success=True, file_path=str(cached))

        logger.info("RJ: baixando comprovante cadastral Certec para CNPJ {}", row.cnpj)
        result = consultar_cadastro_rj(row.cnpj, dest_dir)
        return DownloadResult(success=result.success, file_path=result.file_path, error=result.error)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("RJ: chave NFS-e Nacional para {}", row.id_documento)
            return _nfse_nacional.download_invoice(row, dest_dir)

        logger.info("RJ: codigo curto (Nota Carioca) para {}", row.id_documento)
        from src.browser.playwright_runner import capture_rj_invoice

        return capture_rj_invoice(row, dest_dir)
