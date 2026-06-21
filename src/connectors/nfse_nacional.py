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

        # 1) Caminho REAL e principal: Consulta Pública oficial + hCaptcha (2Captcha).
        #    Baixa o PDF da DANFSe de verdade. É o caminho mais curto que funciona.
        from src.services.nfse_nacional_download import baixar_danfse
        from src.utils.fiscal_keys import decode as _decode
        numero = None
        try:
            ch = _decode(key)
            numero = str(ch.numero) if ch.numero is not None else None
        except Exception:
            pass
        logger.info("NFS-e Nacional: tentando download real da DANFSe para chave {}...", key[:12])
        danfse = baixar_danfse(key, dest_dir, numero=numero)
        if danfse.success:
            return DownloadResult(success=True, file_path=danfse.file_path)
        logger.warning("NFS-e Nacional: download DANFSe falhou ({})", danfse.error)

        # 2) Caminho OFICIAL alternativo: API SEFIN Nacional com certificado ICP-Brasil (mTLS).
        from src.services.sefin_nacional import cert_disponivel, fetch_nfse
        if cert_disponivel():
            logger.info("NFS-e Nacional: tentando XML via SEFIN (mTLS) para chave {}...", key[:10])
            sefin = fetch_nfse(key, dest_dir)
            if sefin.success:
                return DownloadResult(success=True, file_path=sefin.file_path)

        # 3) Sem captcha/cert: captura a consulta pública como evidência (NÃO é sucesso).
        from src.browser.playwright_runner import capture_nfse_nacional
        result = capture_nfse_nacional(row, dest_dir, chave=key)
        return DownloadResult(
            success=False,
            file_path=result.file_path,
            error=danfse.error or "Falha ao baixar DANFSe NFS-e Nacional",
        )
