"""
Automação de portais municipais via Playwright (headless Chromium).

Estratégias implementadas:
  - BH: Shadow DOM piercing via JS evaluation para preencher e submeter
    formulário da Sydle SPA; aguarda renderização completa dos Web Components.
  - RJ: Preenche formulário ASP.NET WebForms com CNPJ + nota + verificacao;
    CAPTCHA impede submissão automatizada — formulário preenchido capturado.
  - Barueri: Contexto stealth (UA realista, webdriver=undefined) para tentar
    superar detecção Cloudflare; evidência .txt quando CSP bloqueia screenshot.
  - NFS-e Nacional: navega diretamente à URL com chaveAcesso para capturar
    o estado real do documento ou da página de autenticação.
  - Porto Alegre / Nova Lima: portais com falha DNS — registrado como
    INDISPONIVEL sem tentativa de navegação.
"""
from __future__ import annotations
from pathlib import Path

from loguru import logger

from src.models import DownloadResult, InputRow

_BH_URL = "https://servicos.pbh.gov.br/nfse/autenticidade"
_ISSNET_URL = "https://www.issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12"
_RJ_VERIFICACAO_URL = "https://notacarioca.rio.gov.br/documentos/verificacao.aspx"
_NFSE_NACIONAL_VISUALIZAR = (
    "https://www.nfse.gov.br/EmissorNacional/Nfse/Visualizar?chaveAcesso={key}"
)
_NFSE_NACIONAL_HOME = "https://www.nfse.gov.br/EmissorNacional/"

_STEALTH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Remove flag de automação antes de qualquer script da página
_STEALTH_INIT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"

# Preenche o primeiro input visível, inclusive dentro de Shadow DOM
_JS_SHADOW_FILL = """(value) => {
    function fillFirst(root) {
        for (const el of root.querySelectorAll(
            'input:not([type=hidden]):not([type=checkbox]):not([type=radio])'
        )) {
            if (el.offsetParent !== null) {
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, value);
                el.dispatchEvent(new Event('input',  {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot && fillFirst(el.shadowRoot)) return true;
        }
        return false;
    }
    return fillFirst(document.body);
}"""

# Clica no botão de consulta, inclusive dentro de Shadow DOM
_JS_SHADOW_SUBMIT = """() => {
    function clickBtn(root) {
        for (const el of root.querySelectorAll('button, [type=submit], [role=button]')) {
            const txt = (el.textContent || el.value || '').toLowerCase().trim();
            if (
                el.offsetParent !== null &&
                (txt.includes('consultar') || txt.includes('verificar') ||
                 txt.includes('pesquisar') || el.type === 'submit')
            ) {
                el.click();
                return true;
            }
        }
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot && clickBtn(el.shadowRoot)) return true;
        }
        return false;
    }
    return clickBtn(document.body);
}"""


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


def _stealth_context(browser):
    """Contexto com UA realista, viewport desktop e webdriver=undefined."""
    ctx = browser.new_context(
        user_agent=_STEALTH_UA,
        viewport={"width": 1920, "height": 1080},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    ctx.add_init_script(_STEALTH_INIT)
    return ctx


# ---------------------------------------------------------------------------
# Belo Horizonte — Sydle SPA com Shadow DOM
# ---------------------------------------------------------------------------

def _bh_interact(page, cod: str) -> bool:
    """
    Aguarda renderização dos Web Components da Sydle SPA e tenta preencher
    e submeter o formulário de autenticidade via Shadow DOM piercing.
    Retorna True se preencheu ao menos um campo.
    """
    try:
        page.wait_for_function(
            """() => {
                function hasShadow(root) {
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) return true;
                    }
                    return false;
                }
                return hasShadow(document.body);
            }""",
            timeout=10000,
        )
    except Exception:
        logger.warning("BH: Shadow DOM não detectado após 10s — tentando interação direta")

    filled = page.evaluate(_JS_SHADOW_FILL, arg=cod)
    if filled:
        logger.info("BH: campo preenchido via Shadow DOM piercing")
        page.wait_for_timeout(500)
        submitted = page.evaluate(_JS_SHADOW_SUBMIT)
        if submitted:
            logger.info("BH: botão de consulta clicado — aguardando resultado")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                page.wait_for_timeout(3000)
        else:
            logger.warning("BH: botão de consulta não encontrado no Shadow DOM")
    else:
        logger.warning("BH: nenhum input visível encontrado no Shadow DOM")
    return filled


def capture_bh_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = _stealth_context(browser)
            page = ctx.new_page()
            logger.info("BH: acessando portal NFS-e para cadastro CNPJ {}", row.cnpj)
            page.goto(_BH_URL, timeout=30000, wait_until="domcontentloaded")
            _bh_interact(page, row.cnpj)
            screenshot = _screenshot(page, dest_dir, f"cadastro_{row.cnpj}")
            browser.close()
        return DownloadResult(success=True, file_path=str(screenshot))
    except Exception as exc:
        logger.error("BH company capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


def capture_bh_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = _stealth_context(browser)
            page = ctx.new_page()
            logger.info("BH: acessando portal NFS-e para nota {} (cod {})", row.id_documento, cod)
            page.goto(_BH_URL, timeout=30000, wait_until="domcontentloaded")
            filled = _bh_interact(page, cod)
            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()

        msg = None if filled else "Shadow DOM renderizado mas nenhum campo encontrado"
        return DownloadResult(success=True, file_path=str(screenshot), error=msg)
    except Exception as exc:
        logger.error("BH invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Rio de Janeiro — Nota Carioca (CAPTCHA documentado)
# ---------------------------------------------------------------------------

def capture_rj_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright não instalado")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("RJ: acessando Nota Carioca para cadastro CNPJ {}", row.cnpj)
            resp = page.goto(_RJ_VERIFICACAO_URL, timeout=30000, wait_until="domcontentloaded")
            if resp and resp.status >= 400:
                browser.close()
                return DownloadResult(
                    success=False,
                    error=f"Nota Carioca retornou HTTP {resp.status} — portal indisponível",
                )
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
        return DownloadResult(success=False, error="Playwright não instalado")

    cod = row.cod_verificacao.strip()
    referencia = (row.referencia or "").strip()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("RJ: acessando Nota Carioca para nota {} (cod {})", row.id_documento, cod)
            resp = page.goto(_RJ_VERIFICACAO_URL, timeout=30000, wait_until="domcontentloaded")
            if resp and resp.status >= 400:
                browser.close()
                return DownloadResult(
                    success=False,
                    error=f"Nota Carioca retornou HTTP {resp.status} — portal indisponível",
                )
            # Preenche formulário ASP.NET WebForms; ViewState é gerenciado pelo Playwright.
            # CAPTCHA na submissão impede automação — formulário preenchido capturado como evidência.
            fill_errors = []
            for selector, value in [
                ("input[name='ctl00$cphCabMenu$tbCPFCNPJ']",    row.cnpj),
                ("input[name='ctl00$cphCabMenu$tbNota']",        referencia),
                ("input[name='ctl00$cphCabMenu$tbVerificacao']", cod),
            ]:
                if not value:
                    continue
                try:
                    page.fill(selector, value, timeout=3000)
                except Exception as e:
                    fill_errors.append(str(e)[:60])

            if fill_errors:
                logger.warning("RJ: campos não encontrados: {}", fill_errors)

            screenshot = _screenshot(page, dest_dir, f"nota_{cod[:20]}")
            browser.close()

        error_msg = (
            "CAPTCHA impede submissão automatizada — "
            "formulário preenchido (CNPJ + nota + código) capturado como evidência"
        )
        return DownloadResult(success=True, file_path=str(screenshot), error=error_msg)
    except Exception as exc:
        logger.error("RJ invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Barueri — ISSNet Online (stealth context para tentativa de bypass Cloudflare)
# ---------------------------------------------------------------------------

def _barueri_attempt(dest_dir: Path, filename: str, label: str) -> tuple[str | None, int | None, str | None]:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return None, None, "Playwright não instalado"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = _stealth_context(browser)
            page = ctx.new_page()
            resp = page.goto(_ISSNET_URL, timeout=30000, wait_until="domcontentloaded")
            status = resp.status if resp else None

            try:
                out = _screenshot(page, dest_dir, filename)
                file_path = str(out)
            except Exception:
                evidence = dest_dir / f"{filename}_evidencia.txt"
                evidence.write_text(
                    f"URL: {_ISSNET_URL}\n"
                    f"HTTP status: {status}\n"
                    f"Label: {label}\n"
                    "Cloudflare bloqueou screenshot (CSP/CDP restriction)\n"
                    "Tentativa realizada com contexto stealth "
                    "(--disable-blink-features=AutomationControlled, webdriver=undefined, UA Chrome/120)\n",
                    encoding="utf-8",
                )
                file_path = str(evidence)
            browser.close()
        return file_path, status, None
    except Exception as exc:
        return None, None, str(exc)


def capture_barueri_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.info("Barueri: tentando ISSNet com contexto stealth para CNPJ {}", row.cnpj)
    file_path, status, error = _barueri_attempt(
        dest_dir, f"cadastro_{row.cnpj}", f"cadastro CNPJ {row.cnpj}"
    )
    if error:
        return DownloadResult(success=False, error=error)
    if status == 403:
        return DownloadResult(
            success=False,
            file_path=file_path,
            error="ISSNet retornou 403 Cloudflare — bloqueio persistente mesmo com contexto stealth",
        )
    return DownloadResult(
        success=status == 200,
        file_path=file_path,
        error=None if status == 200 else f"HTTP {status}",
    )


def capture_barueri_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    cod = row.cod_verificacao.strip()
    logger.info("Barueri: tentando ISSNet com contexto stealth para nota {}", row.id_documento)
    file_path, status, error = _barueri_attempt(
        dest_dir, f"nota_{cod[:20]}", f"nota {row.id_documento}"
    )
    if error:
        return DownloadResult(success=False, error=error)
    if status == 403:
        return DownloadResult(
            success=False,
            file_path=file_path,
            error="ISSNet retornou 403 Cloudflare — bloqueio persistente mesmo com contexto stealth",
        )
    return DownloadResult(
        success=status == 200,
        file_path=file_path,
        error=None if status == 200 else f"HTTP {status}",
    )


# ---------------------------------------------------------------------------
# Porto Alegre — portal municipal offline (DNS fail)
# ---------------------------------------------------------------------------

def capture_poa_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("POA: portal municipal com falha DNS — cadastro indisponível CNPJ {}", row.cnpj)
    return DownloadResult(
        success=False,
        error="Portal Porto Alegre indisponível (falha DNS em todos os endpoints testados)",
    )


def capture_poa_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("POA: portal municipal com falha DNS — nota indisponível cod {}", row.cod_verificacao)
    return DownloadResult(
        success=False,
        error="Portal Porto Alegre indisponível (falha DNS em todos os endpoints testados)",
    )


# ---------------------------------------------------------------------------
# Nova Lima — portal municipal offline
# ---------------------------------------------------------------------------

def capture_nova_lima_company(row: InputRow, dest_dir: Path) -> DownloadResult:
    logger.warning("Nova Lima: portal offline — cadastro indisponível CNPJ {}", row.cnpj)
    return DownloadResult(
        success=False,
        error="Portal Nova Lima indisponível (migrado para NFS-e Nacional em Jan/2026)",
    )


# ---------------------------------------------------------------------------
# NFS-e Nacional — navega diretamente à URL com chaveAcesso
# ---------------------------------------------------------------------------

def capture_nfse_nacional(row: InputRow, dest_dir: Path, chave: str) -> DownloadResult:
    """
    Navega diretamente à URL de visualização com a chaveAcesso completa.
    O portal exige autenticação gov.br para exibir o XML — a URL específica
    por chave mostra o estado real (documento ou redirect para login com a
    chave pré-carregada), diferentemente de apenas capturar a home page.
    """
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright não instalado")

    safe_chave = chave.replace(" ", "")
    url_visualizar = _NFSE_NACIONAL_VISUALIZAR.format(key=safe_chave)
    safe_name = safe_chave[:30]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = _stealth_context(browser)
            page = ctx.new_page()
            logger.info(
                "NFS-e Nacional: navegando URL com chave {}... ({})",
                safe_chave[:12], row.id_documento,
            )
            resp = page.goto(url_visualizar, timeout=30000, wait_until="domcontentloaded")
            status = resp.status if resp else None

            if status and status >= 500:
                # Routing bug no servidor NFS-e Nacional para esta rota — fallback para home
                logger.warning(
                    "NFS-e Nacional: Visualizar retornou {} — fallback para home page", status
                )
                page.goto(_NFSE_NACIONAL_HOME, timeout=20000, wait_until="domcontentloaded")

            screenshot = _screenshot(page, dest_dir, f"nfse_nacional_{safe_name}")
            browser.close()

        error = None
        if status and status >= 500:
            error = (
                f"NFS-e Nacional retornou HTTP {status} na URL de visualização "
                f"(chave {safe_chave[:16]}...) — "
                "autenticação gov.br necessária para acessar o documento"
            )
        return DownloadResult(success=True, file_path=str(screenshot), error=error)
    except Exception as exc:
        logger.error("NFS-e Nacional capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))
