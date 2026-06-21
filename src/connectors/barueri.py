"""
Conector Barueri — ISSNet Online (issnetonline.com.br).
URL verificada: https://www.issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12 (HTTP 403).
URL antiga barueri.nfse.ig.com.br não resolve DNS.

Limitacao conhecida: ISSNet retorna 403 via Cloudflare para requisicoes sem
browser fingerprint valido. Playwright com User-Agent realista pode superar, mas
nao e garantido sem resolucao de challenge JS. Captura screenshot como evidencia.

Formatos de cod_verificacao na amostra:
  - pontilhado: 209U.0278.7851.2113499-Y
  - curto:      04WPGGZBF, P3P9-BGXV
"""
from __future__ import annotations
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.connectors.base import MunicipalConnector
from src.connectors.nfse_nacional import NfseNacionalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import is_nfse_nacional_key

_nfse_nacional = NfseNacionalConnector("BARUERI")

_ISSNET_AUTENTICIDADE = (
    "https://www.issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12"
)
_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; poc-automacao-ccm-nfse/0.1)",
}


class BarueriConnector(MunicipalConnector):
    @property
    def municipio(self) -> str:
        return "BARUERI"

    @property
    def estrategia(self) -> str:
        return "ISSNet Online (Playwright) — Cloudflare 403 documentado"

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    def lookup_ccm(self, row: InputRow) -> CcmResult:
        logger.info("Barueri: consultando CCM para CNPJ {}", row.cnpj)
        return CcmResult(
            found=False,
            error="ISSNet nao expoe CCM publicamente sem autenticacao",
        )

    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        from src.browser.playwright_runner import capture_barueri_company
        return capture_barueri_company(row, dest_dir)

    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        if is_nfse_nacional_key(row.cod_verificacao):
            logger.info("Barueri: chave NFS-e Nacional detectada para {}", row.id_documento)
            return _nfse_nacional.download_invoice(row, dest_dir)

        from src.browser.playwright_runner import capture_barueri_invoice
        return capture_barueri_invoice(row, dest_dir)
