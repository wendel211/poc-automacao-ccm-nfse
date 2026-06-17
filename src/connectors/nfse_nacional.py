"""
Conector para NFS-e Nacional (SEFIN/ABRASF padrão nacional).
Identifica pela chave longa numérica (~50 dígitos).
Documentação: https://www.nfse.gov.br/
"""
from __future__ import annotations
import re
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.connectors.base import MunicipalConnector
from src.models import CcmResult, DownloadResult, InputRow

_BASE_URL = "https://www.nfse.gov.br/EmissorNacional/Contribuinte/NotaFiscal"
_PDF_URL = "https://www.nfse.gov.br/EmissorNacional/Contribuinte/NotaFiscal/Visualizar"

_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; poc-automacao-ccm-nfse/0.1)",
    "Accept": "application/json, text/html, */*",
}


def _clean_key(cod: str) -> str:
    return re.sub(r"\s", "", cod)


class NfseNacionalConnector(MunicipalConnector):
    """
    Estratégia: HTTP direto ao portal NFS-e Nacional para chaves longas.
    Quando a chave curta for identificada, este conector declina e o conector
    municipal próprio assume.
    """

    def __init__(self, municipio_name: str) -> None:
        self._municipio = municipio_name

    @property
    def municipio(self) -> str:
        return self._municipio

    @property
    def estrategia(self) -> str:
        return "API NFS-e Nacional (chave 50+ dígitos)"

    def lookup_ccm(self, row: InputRow) -> CcmResult:
        """
        NFS-e Nacional não expõe CCM diretamente.
        Retorna not-found; o pipeline tenta o conector municipal como fallback.
        """
        return CcmResult(found=False, error="NFS-e Nacional não retorna CCM — use conector municipal")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        return DownloadResult(
            success=False,
            error="Cadastro municipal não disponível via NFS-e Nacional — use conector municipal",
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        key = _clean_key(row.cod_verificacao)
        logger.info("NFS-e Nacional: baixando nota {} (chave {}...)", row.id_documento, key[:10])

        try:
            with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.get(f"{_PDF_URL}?chaveAcesso={key}")

            if resp.status_code == 200 and b"%PDF" in resp.content[:8]:
                out_file = dest_dir / f"{key[:20]}.pdf"
                out_file.write_bytes(resp.content)
                logger.success("Nota baixada: {}", out_file)
                return DownloadResult(success=True, file_path=str(out_file))

            logger.warning(
                "NFS-e Nacional retornou HTTP {} para chave {}", resp.status_code, key[:10]
            )
            return DownloadResult(
                success=False,
                error=f"HTTP {resp.status_code} — portal pode exigir autenticação ou CAPTCHA",
            )

        except httpx.TimeoutException:
            return DownloadResult(success=False, error="Timeout ao conectar ao portal NFS-e Nacional")
        except Exception as exc:
            return DownloadResult(success=False, error=str(exc))
