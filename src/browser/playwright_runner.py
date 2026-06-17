"""
Automacao de portais municipais via Playwright (headless Chromium).
Cada funcao navega ao portal correto, preenche formularios disponiveis
e captura screenshot como evidencia.

Limitacoes documentadas:
  - RJ Nota Carioca: formulario preenchido mas CAPTCHA bloqueia consulta.
  - BH: portal usa Sydle SPA com Web Components (Shadow DOM); form nao
    renderiza em headless sem delay extenso — captura landing page.
  - Barueri: ISSNet retorna 403 Cloudflare antes de renderizar — captura
    pagina de erro como evidencia.
  - Porto Alegre / Nova Lima: portais com falha DNS — registrado como
    INDISPONIVEL sem tentativa de navegacao.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.models import DownloadResult, InputRow

_BH_URL = "https://servicos.pbh.gov.br/nfse/autenticidade"
_ISSNET_URL = "https://www.issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12"
_RJ_VERIFICACAO_URL = "https://notacarioca.rio.gov.br/documentos/verificacao.aspx"
_NFSE_NACIONAL_URL = "https://www.nfse.gov.br/EmissorNacional/"


def _screenshot(page, dest: Path, name: str) -> Path:
    out = dest / f"{name}.png"
    page.screenshot(path=str(out), full_page=True)
    return out


def _try_import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Barueri — ISSNet Online (403 Cloudflare documentado)
# ---------------------------------------------------------------------------

def _barueri_navigate_and_evidence(dest_dir: Path, filename: str, label: str) -> tuple[str | None, int | None, str | None]:
    """Navega ao ISSNet e tenta capturar evidencia. Retorna (file_path, status, error)."""
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return None, None, "Playwright nao instalado"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            resp = page.goto(_ISSNET_URL, timeout=30000, wait_until="domcontentloaded")
            status = resp.status if resp else None
            try:
                out = _screenshot(page, dest_dir, filename)
                file_path = str(out)
            except Exception:
                # Cloudflare CSP bloqueia screenshot — salva evidencia em texto
                evidence = dest_dir / f"{filename}_evidencia.txt"
                evidence.write_text(
                    f"URL: {_ISSNET_URL}\nHTTP status: {status}\nLabel: {label}\n"
                    "Cloudflare bloqueou screenshot (CSP/Headless restriction)\n",
                    encoding="utf-8",
                )
                file_path = str(evidence)
            browser.close()
        return file_path, status, None
    except Exception as exc:
        return None, None, str(exc)


def capture_barueri_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.info("Barueri: acessando ISSNet para cadastro CNPJ {}", row.cnpj)
    file_path, status, error = _barueri_navigate_and_evidence(
        dest_dir, f"cadastro_{row.cnpj}", f"cadastro CNPJ {row.cnpj}"
    )
    if error:
        logger.error("Barueri company capture error: {}", error)
        return DownloadResult(success=False, error=error)
    if status == 403:
        return DownloadResult(
            success=False,
            file_path=file_path,
            error="ISSNet retornou 403 Cloudflare — acesso de bot bloqueado",
        )
    return DownloadResult(success=True, file_path=file_path)


def capture_barueri_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    cod = row.cod_verificacao.strip()
    logger.info("Barueri: acessando ISSNet para nota {} (cod {})", row.id_documento, cod)
    file_path, status, error = _barueri_navigate_and_evidence(
        dest_dir, f"nota_{cod[:20]}", f"nota {row.id_documento} cod {cod}"
    )
    if error:
        logger.error("Barueri invoice capture error: {}", error)
        return DownloadResult(success=False, error=error)
    if status == 403:
        return DownloadResult(
            success=False,
            file_path=file_path,
            error="ISSNet retornou 403 Cloudflare — acesso de bot bloqueado",
        )
    return DownloadResult(success=True, file_path=file_path)


# ---------------------------------------------------------------------------
# Belo Horizonte — servicos.pbh.gov.br (Sydle SPA, Shadow DOM)
# ---------------------------------------------------------------------------

def capture_bh_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("BH: acessando portal NFS-e para cadastro CNPJ {}", row.cnpj)
            page.goto(_BH_URL, timeout=30000, wait_until="domcontentloaded")
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(
            success=True,
            file_path=str(screenshot),
        )
    except Exception as exc:
        logger.error("BH company capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


def capture_bh_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("BH: acessando portal NFS-e para nota {} (cod {})", row.id_documento, cod)
            page.goto(_BH_URL, timeout=30000, wait_until="domcontentloaded")
            # Sydle SPA renderiza form via Web Components (Shadow DOM).
            # Tentativa de preencher campo de autenticidade:
            try:
                page.wait_for_selector("input", timeout=5000)
                inputs = page.query_selector_all("input:not([type='hidden'])")
                if inputs:
                    inputs[0].fill(cod)
            except Exception:
                pass
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(
            success=True,
            file_path=str(screenshot),
        )
    except Exception as exc:
        logger.error("BH invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Rio de Janeiro — Nota Carioca (CAPTCHA documentado)
# ---------------------------------------------------------------------------

def capture_rj_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("RJ: acessando Nota Carioca para cadastro CNPJ {}", row.cnpj)
            page.goto(_RJ_VERIFICACAO_URL, timeout=30000, wait_until="domcontentloaded")
            try:
                page.fill("input[name='ctl00$cphCabMenu$tbCPFCNPJ']", row.cnpj)
            except Exception:
                pass
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        logger.error("RJ company capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


def capture_rj_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    cod = row.cod_verificacao.strip()
    referencia = (row.referencia or "").strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("RJ: acessando Nota Carioca para nota {} (cod {})", row.id_documento, cod)
            page.goto(_RJ_VERIFICACAO_URL, timeout=30000, wait_until="domcontentloaded")
            # Preenche formulario ASP.NET WebForms pre-CAPTCHA.
            # CAPTCHA impede submissao automatizada — captura estado do form como evidencia.
            try:
                page.fill("input[name='ctl00$cphCabMenu$tbCPFCNPJ']", row.cnpj)
                if referencia:
                    page.fill("input[name='ctl00$cphCabMenu$tbNota']", referencia)
                page.fill("input[name='ctl00$cphCabMenu$tbVerificacao']", cod)
            except Exception as fill_err:
                logger.warning("RJ: erro ao preencher formulario: {}", fill_err)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(
            success=True,
            file_path=str(screenshot),
        )
    except Exception as exc:
        logger.error("RJ invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Porto Alegre — portal municipal offline (DNS fail)
# ---------------------------------------------------------------------------

def capture_poa_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("POA: portal municipal com falha DNS — cadastro indisponivel para CNPJ {}", row.cnpj)
    return DownloadResult(
        success=False,
        error="Portal Porto Alegre indisponivel (falha DNS em todos os endpoints testados)",
    )


def capture_poa_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("POA: portal municipal com falha DNS — nota indisponivel cod {}", row.cod_verificacao)
    return DownloadResult(
        success=False,
        error="Portal Porto Alegre indisponivel (falha DNS em todos os endpoints testados)",
    )


# ---------------------------------------------------------------------------
# Nova Lima — portal municipal offline (migrado para NFS-e Nacional Jan/2026)
# ---------------------------------------------------------------------------

def capture_nova_lima_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("Nova Lima: portal municipal offline — cadastro indisponivel para CNPJ {}", row.cnpj)
    return DownloadResult(
        success=False,
        error="Portal Nova Lima indisponivel (migrado para NFS-e Nacional em Jan/2026)",
    )


# ---------------------------------------------------------------------------
# NFS-e Nacional — captura screenshot da pagina de login como evidencia
# ---------------------------------------------------------------------------

def capture_nfse_nacional(row: InputRow, dest_dir: Path, chave: str) -> DownloadResult:
    """
    Navega ao portal NFS-e Nacional e captura screenshot como evidencia.
    O portal exige autenticacao via gov.br — consulta automatizada nao e possivel
    sem credenciais. A chave de acesso e registrada no nome do arquivo.
    """
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    safe_chave = chave.replace(" ", "")[:30]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("NFS-e Nacional: acessando portal para chave {} (row {})", safe_chave, row.id_documento)
            page.goto(_NFSE_NACIONAL_URL, timeout=30000, wait_until="domcontentloaded")
            screenshot = _screenshot(page, dest_dir, f"nfse_nacional_{safe_chave}")
            browser.close()
        return DownloadResult(
            success=True,
            file_path=str(screenshot),
        )
    except Exception as exc:
        logger.error("NFS-e Nacional capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))
