"""
Conector Barueri — Portal NFS-e Barueri.
Portal: https://barueri.nfse.ig.com.br/
Estratégia:
  - Verificação de autenticidade via HTTP (formulário público).
  - CCM consultado via Playwright quando não disponível por API.
  - Código de verificação aparece em dois formatos na amostra:
      1. formato com pontos/hífen: 209U.0278.7851.2113499-Y
      2. código curto: 04WPGGZBF, P3P9-BGXV
"""
from __future__ import annotations
from pathlib import Path

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.connectors.base import MunicipalConnector
from src.models import CcmResult, DownloadResult, InputRow
from src.utils.cnpj import normalize as norm_cnpj

_PORTAL = "https://barueri.nfse.ig.com.br"
_CONSULTA_URL = f"{_PORTAL}/contribuinte/NfseConsulta.aspx"
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
        return "HTTP portal Barueri NFS-e + Playwright fallback"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def lookup_ccm(self, row: InputRow) -> CcmResult:
        """
        Tenta consultar CCM/IM pelo CNPJ via portal Barueri.
        O portal não expõe CCM publicamente sem autenticação — registra como indisponível
        e o campo fica para preenchimento manual ou automação com login.
        """
        logger.info("Barueri: consultando CCM para CNPJ {}", row.cnpj)
        try:
            with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.get(_CONSULTA_URL)
            if resp.status_code == 200:
                logger.warning("Barueri: CCM não exposto publicamente — requer login")
                return CcmResult(
                    found=False,
                    error="Portal Barueri requer autenticação para consulta de CCM",
                )
            return CcmResult(found=False, error=f"HTTP {resp.status_code}")
        except httpx.TimeoutException:
            return CcmResult(found=False, error="Timeout ao acessar portal Barueri")
        except Exception as exc:
            return CcmResult(found=False, error=str(exc))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_company_registration(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        """Screenshot do cadastro via Playwright (implementado em playwright_runner)."""
        from src.browser.playwright_runner import capture_barueri_company
        return capture_barueri_company(row, dest_dir)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_invoice(self, row: InputRow, dest_dir: Path) -> DownloadResult:
        """Consulta de autenticidade da nota via portal Barueri."""
        cod = row.cod_verificacao.strip()
        logger.info("Barueri: baixando nota {} (cod {})", row.id_documento, cod)
        try:
            with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                resp = client.post(
                    _CONSULTA_URL,
                    data={"txtCodVerificacao": cod, "btnConsultar": "Consultar"},
                )
            if resp.status_code == 200:
                if b"%PDF" in resp.content[:8]:
                    out_file = dest_dir / f"{cod.replace('.', '').replace('-', '')}.pdf"
                    out_file.write_bytes(resp.content)
                    return DownloadResult(success=True, file_path=str(out_file))
                # Portal retornou HTML — salva como evidência para análise
                out_file = dest_dir / f"{cod.replace('.', '').replace('-', '')}_response.html"
                out_file.write_bytes(resp.content)
                logger.warning("Barueri: resposta em HTML (não PDF) — salvo como evidência")
                return DownloadResult(
                    success=False,
                    file_path=str(out_file),
                    error="Portal retornou HTML em vez de PDF — pode exigir sessão ou CAPTCHA",
                )
            return DownloadResult(success=False, error=f"HTTP {resp.status_code}")
        except httpx.TimeoutException:
            return DownloadResult(success=False, error="Timeout ao acessar portal Barueri")
        except Exception as exc:
            return DownloadResult(success=False, error=str(exc))
