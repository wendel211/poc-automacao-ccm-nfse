"""Cadastro municipal de Nova Lima via portal oficial e-NFS.

A inscricao municipal e confirmada pela Consulta de Prestadores publica do e-NFS
(servlet `servicosportaljson`). O comprovante de cadastro e o **print da pagina de
Consulta de Prestadores** (aceito pelo enunciado: "PDF/XML ou Print da Pagina de
Cadastro"), capturado com Playwright mostrando razao social, CNPJ e Inscricao
Municipal na pagina oficial. Nada e fabricado localmente.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

PORTAL_URL = "https://e-nfs.com.br/e-nfs_novalima/portal/"
PRESTADORES_URL = "https://e-nfs.com.br/e-nfs_novalima/servlet/servicosportaljson"

_SALT_CNPJ = "56422955000191"


@dataclass
class NovaLimaCadastroResult:
    success: bool
    inscricao: Optional[str] = None
    razao: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None


def consultar_inscricao_nova_lima(cnpj: str, razao_hint: str | None = None) -> NovaLimaCadastroResult:
    """Consulta a inscricao municipal no portal e-NFS de Nova Lima."""
    criterios = [cnpj]
    if razao_hint:
        criterios.append(razao_hint)
    if cnpj == _SALT_CNPJ:
        criterios.append("SALT TECNOLOGIA")

    try:
        with httpx.Client(timeout=30.0, verify=False, follow_redirects=True) as client:
            for criterio in criterios:
                resp = client.post(
                    PRESTADORES_URL,
                    data={
                        "acao": "CNSPRESTADORES",
                        "criterioconsulta": criterio,
                        "pagenumber": "1",
                    },
                    headers={"Referer": PORTAL_URL},
                )
                resp.raise_for_status()
                for item in resp.json():
                    if str(item.get("CtcCpfCnpj") or "") == cnpj:
                        inscricao = _format_cmc(item.get("CtcCmc"))
                        if inscricao:
                            return NovaLimaCadastroResult(
                                success=True,
                                inscricao=inscricao,
                                razao=str(item.get("CtcRazSocial") or "").strip() or None,
                            )
        return NovaLimaCadastroResult(success=False, error="Inscricao municipal nao encontrada no e-NFS Nova Lima")
    except Exception as exc:  # noqa: BLE001
        return NovaLimaCadastroResult(success=False, error=str(exc))


def baixar_cadastro_nova_lima(cnpj: str, dest_dir: Path) -> NovaLimaCadastroResult:
    """Captura o print oficial da Consulta de Prestadores do e-NFS Nova Lima."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    consulta = consultar_inscricao_nova_lima(cnpj)
    if not consulta.success:
        return consulta

    out = dest_dir / f"cadastro_municipal_nova_lima_enfs_{cnpj}.png"
    if out.exists() and out.stat().st_size > 1000:
        logger.info("Nova Lima: reutilizando print da Consulta de Prestadores {}", out.name)
        return NovaLimaCadastroResult(
            success=True, inscricao=consulta.inscricao, razao=consulta.razao, file_path=str(out)
        )

    termo = (consulta.razao or cnpj).strip()
    capturado = _capturar_print_enfs(cnpj, consulta.inscricao or "", termo, out)
    if capturado:
        logger.success("Nova Lima: print da Consulta de Prestadores salvo -> {}", out.name)
        return NovaLimaCadastroResult(
            success=True, inscricao=consulta.inscricao, razao=consulta.razao, file_path=str(out)
        )

    return NovaLimaCadastroResult(
        success=False,
        inscricao=consulta.inscricao,
        razao=consulta.razao,
        error="Inscricao confirmada no e-NFS, mas nao foi possivel capturar o print da Consulta de Prestadores",
    )


def _capturar_print_enfs(cnpj: str, inscricao: str, termo_busca: str, out: Path) -> bool:
    """Abre a Consulta de Prestadores oficial, pesquisa e printa a pagina.

    Valida que a pagina renderizada contem a inscricao e o CNPJ antes de salvar —
    garante que o print corresponde ao prestador correto (sem fabricar nada).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        logger.warning("Nova Lima: Playwright ausente ({})", exc)
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(PORTAL_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1500)
            page.fill("#criterioconsulta", termo_busca)
            page.click('button[ng-click="consultarPrestadores(criterioconsulta, 1, 1)"]')
            try:
                page.wait_for_function(
                    "(im) => document.body.innerText.includes(im)", arg=inscricao, timeout=20000
                )
            except Exception:
                pass
            page.wait_for_timeout(800)

            body = page.inner_text("body")
            if inscricao not in body or cnpj not in body.replace(".", "").replace("/", "").replace("-", ""):
                browser.close()
                return False

            out.parent.mkdir(parents=True, exist_ok=True)
            el = page.query_selector("xpath=//*[@id='criterioconsulta']/ancestor::section[1]")
            if el is not None:
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                el.screenshot(path=str(out))
            else:
                page.screenshot(path=str(out), full_page=True)
            browser.close()
        return out.exists() and out.stat().st_size > 1000
    except Exception as exc:  # noqa: BLE001
        logger.error("Nova Lima: erro ao capturar print e-NFS: {}", exc)
        return False


def _format_cmc(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float):
        value = int(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits or None
