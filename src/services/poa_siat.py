"""Porto Alegre SIAT ISSQN registration proof downloader."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from src.services.captcha_solver import solve_recaptcha

SIAT_URL = "https://siat.procempa.com.br/siat/CpsEmitirComprovanteInscricao_Internet.do"
RECAPTCHA_SITEKEY = "6LcJrQcTAAAAABQRp3xSdl6rAqKkxp0XE47zpC1t"
_INSCRICAO_RE = re.compile(r"\b(\d{3}\.\d{3}\.\d\.\d)\b")


@dataclass
class SiatResult:
    success: bool
    inscricao: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None


def consultar_comprovante_issqn_poa(cnpj: str, dest_dir: Path) -> SiatResult:
    """Baixa o comprovante municipal ISSQN de Porto Alegre por CNPJ."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"cadastro_municipal_poa_issqn_{cnpj}.pdf"
    if out.exists() and out.stat().st_size > 1000:
        inscricao = _extract_inscricao_from_pdf(out)
        if inscricao:
            logger.info("POA SIAT: reutilizando comprovante ISSQN {}", out.name)
            return SiatResult(success=True, inscricao=inscricao, file_path=str(out))

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return SiatResult(success=False, error=f"Playwright ausente: {exc}")

    token = solve_recaptcha(RECAPTCHA_SITEKEY, SIAT_URL)
    if not token:
        return SiatResult(success=False, error="reCAPTCHA SIAT POA nao resolvido")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1366, "height": 900},
                accept_downloads=True,
            )
            page.goto(SIAT_URL, wait_until="networkidle", timeout=60000)
            page.select_option("select", label="CNPJ")
            page.locator("input.gwt-TextBox").first.fill(cnpj)
            _confirm_recaptcha(page, token)

            try:
                with page.expect_download(timeout=90000) as download_info:
                    page.locator('div[role="button"]').nth(0).click()
                download = download_info.value
                download.save_as(str(out))
            except PlaywrightTimeoutError:
                error = _short_error(page.inner_text("body"), "SIAT POA nao retornou download")
                browser.close()
                return SiatResult(success=False, error=error)

            browser.close()

        if out.read_bytes()[:4] != b"%PDF":
            return SiatResult(success=False, error="Comprovante SIAT POA nao retornou PDF valido")
        inscricao = _extract_inscricao_from_pdf(out)
        if not inscricao:
            return SiatResult(success=False, file_path=str(out), error="Inscricao ISSQN nao encontrada no PDF")
        logger.success("POA SIAT: comprovante ISSQN baixado -> {} ({})", out.name, inscricao)
        return SiatResult(success=True, inscricao=inscricao, file_path=str(out))
    except Exception as exc:  # noqa: BLE001
        logger.error("POA SIAT: erro no comprovante ISSQN: {}", exc)
        return SiatResult(success=False, error=str(exc))


def _confirm_recaptcha(page, token: str) -> None:
    page.evaluate(
        """token => {
            document.querySelectorAll('textarea[name^="g-recaptcha-response"]').forEach(t => {
                t.value = token;
                t.innerHTML = token;
            });

            function walk(o, depth) {
                if (!o || depth > 6 || typeof o !== 'object') return;
                for (const k of Object.keys(o)) {
                    let v;
                    try { v = o[k]; } catch (e) { continue; }
                    if (typeof v === 'function' && (k === 'callback' || k === 'promise-callback')) {
                        try { v(token); } catch (e) {}
                    } else {
                        walk(v, depth + 1);
                    }
                }
            }
            walk(window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients, 0);
        }""",
        token,
    )


def _extract_inscricao_from_pdf(path: Path) -> Optional[str]:
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:  # noqa: BLE001
        return None

    match = _INSCRICAO_RE.search(text)
    if not match:
        return None
    return match.group(1)


def _short_error(text: str, fallback: str) -> str:
    clean = " ".join(text.split())
    if "É obrigatório confirmar o captcha" in clean or "obrigatório confirmar o captcha" in clean:
        return "SIAT POA recusou o reCAPTCHA"
    return clean[-300:] if clean else fallback
