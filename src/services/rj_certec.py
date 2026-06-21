"""Consulta oficial Certec/Rio para comprovante cadastral de ISS."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

CERTEC_URL = "https://certec.apps.rio.gov.br/"
_IM_RE = re.compile(r"\b(\d{6,8})\b")


@dataclass
class CertecResult:
    success: bool
    inscricao: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None


def consultar_cadastro_rj(cnpj: str, dest_dir: Path | None = None) -> CertecResult:
    """Consulta CNPJ no Certec e opcionalmente salva o comprovante como PDF."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return CertecResult(success=False, error=f"Playwright ausente: {exc}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page()
            page.goto(CERTEC_URL, wait_until="domcontentloaded", timeout=60000)

            if not _wait_for_form(page):
                text = page.inner_text("body")
                browser.close()
                return CertecResult(success=False, error=_short_error(text, "Certec RJ nao carregou o formulario"))

            page.locator('input[value="cnpj"]').check(force=True)
            page.locator('input[placeholder="Digite o CNPJ"]').fill(cnpj)
            page.get_by_text("Enviar", exact=True).click()

            try:
                page.wait_for_function(
                    "() => document.body.innerText.includes('possui as Inscrições') || "
                    "document.body.innerText.includes('Inscrições Municipais abaixo') || "
                    "document.body.innerText.includes('não possui') || "
                    "document.body.innerText.includes('sessão expirou')",
                    timeout=12000,
                )
            except Exception:
                pass

            text = page.inner_text("body")
            if "sessão expirou" in text.lower():
                browser.close()
                return CertecResult(success=False, error="Sessao Certec expirada durante consulta")

            inscricao = _extract_inscricao(text)
            if not inscricao:
                browser.close()
                return CertecResult(success=False, error=_short_error(text, "Inscricao Municipal RJ nao encontrada"))

            page.get_by_text(inscricao, exact=True).click()
            try:
                page.wait_for_function(
                    "() => document.body.innerText.includes('Para impressão do Comprovante')",
                    timeout=12000,
                )
            except Exception:
                pass

            detail_text = page.inner_text("body")
            if "Para impressão do Comprovante" not in detail_text:
                browser.close()
                return CertecResult(success=False, inscricao=inscricao, error="Detalhe Certec nao exibiu comprovante")

            out = None
            if dest_dir is not None:
                dest_dir.mkdir(parents=True, exist_ok=True)
                out = dest_dir / f"cadastro_municipal_rj_certec_{cnpj}.pdf"
                page.pdf(path=str(out), format="A4", print_background=True)

            browser.close()
            return CertecResult(success=True, inscricao=inscricao, file_path=str(out) if out else None)
    except Exception as exc:  # noqa: BLE001
        logger.error("Certec RJ error: {}", exc)
        return CertecResult(success=False, error=str(exc))


def _wait_for_form(page) -> bool:
    for _ in range(15):
        text = page.inner_text("body")
        if "Tipo de Pesquisa" in text:
            return True
        if "sessão expirou" in text.lower():
            return False
        page.wait_for_timeout(1000)
    return False


def _extract_inscricao(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if line == "Inscrição" and i + 1 < len(lines):
            match = _IM_RE.fullmatch(lines[i + 1])
            if match:
                return match.group(1)
    for line in lines:
        match = _IM_RE.fullmatch(line)
        if match:
            return match.group(1)
        match = re.match(r"^(\d{6,8})\s+", line)
        if match:
            return match.group(1)
    return None


def _short_error(text: str, fallback: str) -> str:
    clean = " ".join(text.split())
    return clean[:180] if clean else fallback
