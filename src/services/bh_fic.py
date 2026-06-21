"""Public BH FIC lookup: municipal registration card by CNPJ."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from src.services.captcha_solver import solve as solve_captcha

FIC_URL = "https://mobiliarioonline.pbh.gov.br/mobiliario-cadastro-publico/f/t/emiteficwebsel"
_MAX_RETRIES = 8
_IM_RE = re.compile(r"\b(\d{11})\b")


@dataclass
class FicResult:
    success: bool
    ccm: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None


def consultar_fic_bh(cnpj: str, dest_dir: Path | None = None) -> FicResult:
    """Consult BH public FIC by CNPJ and optionally save the returned page as PDF."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return FicResult(success=False, error=f"Playwright ausente: {exc}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            last_error = "FIC nao localizada"

            for attempt in range(1, _MAX_RETRIES + 1):
                page.goto(FIC_URL, wait_until="domcontentloaded", timeout=45000)
                page.fill("#corpo\\:formulario\\:identificador", cnpj)

                captcha_img = page.locator("#captcha1_1").screenshot()
                captcha_text = solve_captcha(captcha_img)
                if not captcha_text:
                    last_error = "Captcha da FIC BH nao resolvido"
                    continue

                logger.info("BH FIC {}: captcha tentativa {}", cnpj, attempt)
                page.fill("#corpo\\:formulario\\:respostaCaptcha", captcha_text)
                page.keyboard.press("F9")
                page.wait_for_timeout(3500)

                text = page.inner_text("body")
                if _captcha_failed(text):
                    last_error = "Captcha da FIC BH recusado pelo portal"
                    continue

                ccm = _extract_ccm(text, cnpj)
                if not ccm:
                    last_error = _extract_error(text) or "Inscricao Municipal nao encontrada na FIC BH"
                    break

                out = None
                if dest_dir is not None:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    out = dest_dir / f"cadastro_municipal_bh_fic_{cnpj}.pdf"
                    page.pdf(path=str(out), format="A4", print_background=True)

                browser.close()
                return FicResult(success=True, ccm=ccm, file_path=str(out) if out else None)

            browser.close()
            return FicResult(success=False, error=last_error)
    except Exception as exc:  # noqa: BLE001
        return FicResult(success=False, error=str(exc))


def _captcha_failed(text: str) -> bool:
    low = text.lower()
    return "codigo invalido" in low or "código inválido" in low or "captcha" in low and "inv" in low


def _extract_ccm(text: str, cnpj: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    active_ccm = _extract_active_ccm(lines, cnpj)
    if active_ccm:
        return active_ccm

    for i, line in enumerate(lines):
        if re.sub(r"\D", "", line) == cnpj:
            for prior in reversed(lines[max(0, i - 5):i]):
                match = _IM_RE.fullmatch(re.sub(r"\D", "", prior))
                if match:
                    return match.group(1)
    match = _IM_RE.search(text)
    return match.group(1) if match else None


def _extract_active_ccm(lines: list[str], cnpj: str) -> Optional[str]:
    row_candidates: list[tuple[str, bool]] = []
    for line in lines:
        digits = re.sub(r"\D", "", line)
        if cnpj not in digits:
            continue
        match = _IM_RE.search(line)
        if not match:
            continue
        upper = line.upper()
        row_candidates.append((match.group(1), "ATIVA" in upper and "BAIXADA" not in upper))

    for ccm, is_active in row_candidates:
        if is_active:
            return ccm

    candidates: list[tuple[str, bool]] = []
    im_indices = [
        i
        for i, line in enumerate(lines)
        if _IM_RE.search(line)
    ]

    for i, line in enumerate(lines):
        if cnpj not in re.sub(r"\D", "", line):
            continue

        prior_ims = [idx for idx in im_indices if idx < i]
        if not prior_ims:
            continue
        im_idx = prior_ims[-1]
        match = _IM_RE.search(lines[im_idx])
        if not match:
            continue
        ccm = match.group(1)

        next_ims = [idx for idx in im_indices if idx > im_idx]
        end = next_ims[0] if next_ims else min(len(lines), i + 12)
        context = " ".join(lines[im_idx:end]).upper()
        candidates.append((ccm, "ATIVA" in context and "BAIXADA" not in context))

    for ccm, is_active in candidates:
        if is_active:
            return ccm
    return None


def _extract_error(text: str) -> Optional[str]:
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) > 8 and ("erro" in clean.lower() or "alerta" in clean.lower()):
            return clean[:180]
    return None
