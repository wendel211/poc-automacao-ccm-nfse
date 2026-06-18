"""
Conector para NFS-e Nacional (SEFIN/ABRASF padrao nacional).
Identifica pela chave longa numerica (40+ digitos).

Estrategia:
  - HTTP GET direto retorna HTTP 500 (portal exige sessao autenticada).
  - Playwright: navega ao portal, captura screenshot da pagina de login
    como evidencia. Autenticacao via gov.br nao e automatizavel sem
    credenciais — registrado como limitacao conhecida.
"""
from __future__ import annotations
import re
from pathlib import Path

from loguru import logger

from src.connectors.base import MunicipalConnector
from src.models import CcmResult, DownloadResult, InputRow


def _clean_key(cod: str) -> str:
    return re.sub(r"\s", "", cod)


class NfseNacionalConnector(MunicipalConnector):
    def __init__(self, municipio_name: str) -> None:
        self._municipio = municipio_name

    @property
    def municipio(self) -> str:
        return self._municipio

    @property
    def estrategia(self) -> str:
        return "NFS-e Nacional (Playwright screenshot — auth gov.br requerida)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        return CcmResult(
            found=False,
            error="NFS-e Nacional nao retorna CCM — use conector municipal",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        return DownloadResult(
            success=False,
            error="Cadastro municipal nao disponivel via NFS-e Nacional",
        )

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        key = _clean_key(row.cod_verificacao)

        # 1) Caminho OFICIAL: API SEFIN Nacional com certificado ICP-Brasil (mTLS).
        #    Baixa o XML real da NFS-e quando um e-CNPJ está configurado no ambiente.
        from src.services.sefin_nacional import cert_disponivel, fetch_nfse
        if cert_disponivel():
            logger.info("NFS-e Nacional: baixando XML via SEFIN (mTLS) para chave {}...", key[:10])
            sefin = fetch_nfse(key, dest_dir)
            if sefin.success:
                return DownloadResult(success=True, file_path=sefin.file_path)
            logger.warning("NFS-e Nacional: SEFIN falhou ({}), caindo para evidência", sefin.error)

        # 2) Sem certificado: captura a consulta pública oficial como evidência.
        logger.info(
            "NFS-e Nacional: capturando evidencia via Playwright para chave {}... ({})",
            key[:10], row.id_documento,
        )
        from src.browser.playwright_runner import capture_nfse_nacional
        result = capture_nfse_nacional(row, dest_dir, chave=key)
        if result.success:
            return DownloadResult(success=True, file_path=result.file_path)
        return DownloadResult(
            success=False,
            error=result.error or "Falha ao capturar evidencia NFS-e Nacional",
        )
