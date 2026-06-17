"""
Automação de portais municipais via Playwright (headless Chromium).
Cada função representa a sequência de passos para um portal específico.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.models import DownloadResult, InputRow


def _screenshot(page, dest: Path, name: str) -> Path:
    out = dest / f"{name}.png"
    page.screenshot(path=str(out), full_page=True)
    return out


# ---------------------------------------------------------------------------
# Barueri
# ---------------------------------------------------------------------------

def capture_barueri_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado — execute: pip install playwright && playwright install chromium")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://barueri.nfse.ig.com.br/contribuinte/NfseConsulta.aspx", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        logger.error("Barueri company capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


def capture_barueri_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://barueri.nfse.ig.com.br/contribuinte/NfseConsulta.aspx", timeout=30000)
            page.fill("input[id*='txtCodVerificacao'], input[name*='cod']", cod)
            page.click("input[type='submit'], button[type='submit']")
            page.wait_for_load_state("networkidle", timeout=15000)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        logger.error("Barueri invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Belo Horizonte — BHISS Digital
# ---------------------------------------------------------------------------

def capture_bh_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://bhiss.pbh.gov.br/nfse/faces/pages/autenticidade/consultaAutenticidade.xhtml", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


def capture_bh_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://bhiss.pbh.gov.br/nfse/faces/pages/autenticidade/consultaAutenticidade.xhtml", timeout=30000)
            try:
                page.fill("input[id*='codAutenticidade'], input[id*='codigo']", cod)
                page.click("input[type='submit'], button[type='submit']")
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Rio de Janeiro — Nota Carioca
# ---------------------------------------------------------------------------

def capture_rj_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://notacarioca.rio.gov.br/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


def capture_rj_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://notacarioca.rio.gov.br/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Porto Alegre
# ---------------------------------------------------------------------------

def capture_poa_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nfse.portoalegre.rs.gov.br/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


def capture_poa_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nfse.portoalegre.rs.gov.br/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Nova Lima
# ---------------------------------------------------------------------------

def capture_nova_lima_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nfse.novalima.mg.gov.br/contribuinte/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))


def capture_nova_lima_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://nfse.novalima.mg.gov.br/contribuinte/", timeout=30000)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        return DownloadResult(success=False, error=str(exc))
