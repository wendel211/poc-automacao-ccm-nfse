"""
Download real de NFS-e em portais municipais do tipo JSF (Porto Alegre e Belo
Horizonte usam a mesma estrutura: cnpjPrestador + numeroNfsE + codVerif, com
captcha de imagem no caso de BH).

Fluxo:
  1. abre o portal
  2. preenche CNPJ do prestador, número (formato AAAA/N) e código de verificação
  3. se houver captcha, lê com ddddocr e tenta; em caso de recusa, recarrega a
     imagem e tenta de novo (várias vezes)
  4. ao obter a nota, salva como PDF (impressão da página)
  5. devolve sucesso só se a nota foi de fato exibida/baixada

Honestidade: se faltam dados (ano/número) ou a nota não existe no portal, devolve
o motivo exato — nunca marca sucesso sem o arquivo.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

# Portais com a mesma estrutura JSF
PORTAL_POA = "https://nfe-web.portoalegre.rs.gov.br/nfse/pages/consultaNFS-e_cidadao.jsf"
PORTAL_BH = "https://bhissdigital.pbh.gov.br/nfse/pages/consultaNFS-e_cidadao_creditoIPTU.jsf"

_MAX_CAPTCHA_RETRIES = 6
# Marcadores de erro retornados pelo portal (significam que NÃO baixou)
_ERRO_MARKERS = (
    "Ocorreu um erro inesperado",
    "Mensagens de Erro",
    "Mensagens de Alerta",
    "não localizou nenhum registro",
    "nao localizou nenhum registro",
    "não é válido",
    "nao e valido",
    "incorreto",
    "não foi encontrada",
    "nao foi encontrada",
    "não localizada",
    "CAMPOS DE PREENCHIMENTO OBRIGAT",
)
_SUCCESS_MARKER = "NFS-e - NOTA FISCAL DE SERVI"


@dataclass
class NotaDownload:
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


def _captcha_bytes(page):
    el = page.query_selector("#form\\:img_captcha")
    if not el:
        return None
    try:
        return el.screenshot()
    except Exception:
        return None


def _tem_erro(texto: str) -> Optional[str]:
    low = texto.lower()
    for m in _ERRO_MARKERS:
        if m.lower() in low:
            # devolve a linha de erro mais informativa
            for linha in texto.splitlines():
                if m.lower() in linha.lower() and len(linha.strip()) > 8:
                    return linha.strip()[:160]
            return m
    return None


def baixar_nota(
    portal_url: str,
    cnpj_prestador: str,
    numero_aaaa_n: str,
    cod_verif: str,
    dest_dir: Path,
    nome_arquivo: str,
    tem_captcha: bool,
) -> NotaDownload:
    """Tenta baixar a NFS-e no portal JSF. Salva PDF se a nota for exibida."""
    try:
        from playwright.sync_api import sync_playwright
        from src.services.captcha_solver import solve as solve_captcha
    except ImportError as e:
        return NotaDownload(success=False, error=f"Dependência ausente: {e}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = dest_dir / f"{nome_arquivo}.pdf"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            ultimo_erro = "Falha desconhecida"

            tentativas = _MAX_CAPTCHA_RETRIES if tem_captcha else 1
            for tentativa in range(1, tentativas + 1):
                page.goto(portal_url, timeout=40000, wait_until="domcontentloaded")
                page.fill('input[name="form:cnpjPrestador"]', cnpj_prestador)
                page.fill('input[name="form:numeroNfsE"]', numero_aaaa_n)
                page.fill('input[name="form:codVerif"]', cod_verif)

                if tem_captcha:
                    img = _captcha_bytes(page)
                    if not img:
                        ultimo_erro = "Imagem de captcha não encontrada"
                        break
                    texto = solve_captcha(img)
                    if not texto:
                        ultimo_erro = "ddddocr não leu o captcha"
                        continue
                    campo = page.query_selector('input[name="j_captcha_response"]')
                    if campo:
                        campo.fill(texto)
                    logger.info("{}: captcha tentativa {} -> {!r}", nome_arquivo, tentativa, texto)

                page.keyboard.press("Enter")
                page.wait_for_timeout(3500)
                corpo = page.inner_text("body")

                erro = _tem_erro(corpo)
                if erro:
                    ultimo_erro = erro
                    # captcha errado -> tenta de novo; outro erro -> não adianta repetir
                    if "imagem de seguran" in erro.lower() or "captcha" in erro.lower():
                        continue
                    if "não é válido" in erro.lower() or "nao e valido" in erro.lower():
                        # erro de dado (número/formato) — não resolve repetindo
                        break
                    break

                validacao = _validar_nota_exibida(corpo, cnpj_prestador, cod_verif)
                if validacao:
                    ultimo_erro = validacao
                    break

                # Sem erro: a nota foi exibida -> salva como PDF
                page.pdf(path=str(out_pdf), format="A4", print_background=True)
                browser.close()
                logger.success("{}: NFS-e baixada -> {}", nome_arquivo, out_pdf.name)
                return NotaDownload(success=True, file_path=str(out_pdf))

            browser.close()
            return NotaDownload(success=False, error=ultimo_erro)
    except Exception as exc:  # noqa: BLE001
        logger.error("{}: erro no download da NFS-e: {}", nome_arquivo, exc)
    return NotaDownload(success=False, error=str(exc))


def _validar_nota_exibida(texto: str, cnpj_prestador: str, cod_verif: str) -> Optional[str]:
    normalized = _normalize(texto)
    if _SUCCESS_MARKER.lower() not in normalized.lower():
        return "Portal municipal nao exibiu uma NFS-e valida"

    cnpj_digits = "".join(c for c in cnpj_prestador if c.isdigit())
    body_digits = "".join(c for c in texto if c.isdigit())
    if cnpj_digits and cnpj_digits not in body_digits:
        return "NFS-e exibida nao contem o CNPJ do prestador esperado"

    if cod_verif and cod_verif.strip().lower() not in texto.lower():
        return "NFS-e exibida nao contem o codigo de verificacao esperado"

    return None


def _normalize(texto: str) -> str:
    return (
        texto.replace("Ç", "C")
        .replace("ç", "c")
        .replace("Ã‡", "C")
        .replace("Ã§", "c")
    )
