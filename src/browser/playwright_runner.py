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

# Evidência visual (screenshot/.txt) é considerada RUÍDO pelo critério atual:
# o pipeline mantém apenas artefatos REAIS (cadastro municipal e nota PDF/XML).
# Mantido como flag para reativar evidência sob demanda em depuração.
_SAVE_EVIDENCE = False

_BH_URL = "https://servicos.pbh.gov.br/nfse/autenticidade"
_ISSNET_URL = "https://www.issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12"
_RJ_VERIFICACAO_URL = "https://notacarioca.rio.gov.br/documentos/verificacao.aspx"
_NFSE_NACIONAL_VISUALIZAR = (
    "https://www.nfse.gov.br/EmissorNacional/Nfse/Visualizar?chaveAcesso={key}"
)
_NFSE_NACIONAL_HOME = "https://www.nfse.gov.br/EmissorNacional/"
# Consulta pública oficial (aceita a chave na query string e renderiza a página
# da nota específica — evidência muito melhor que a home de login).
_NFSE_NACIONAL_CONSULTA = "https://www.nfse.gov.br/consultapublica/?tpc=1&chave={key}"

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


def _screenshot(page, dest: Path, name: str) -> Path | None:
    """Captura screenshot apenas quando a evidência visual está habilitada.

    Por padrão (`_SAVE_EVIDENCE = False`) não grava nada: o pipeline mantém só
    artefatos REAIS (cadastro municipal e nota PDF/XML).
    """
    if not _SAVE_EVIDENCE:
        return None
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
        return DownloadResult(
            success=False,
            file_path=str(screenshot) if screenshot else None,
            error="Apenas screenshot do portal BH; cadastro municipal/CCM nao foi baixado",
        )
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

        msg = (
            "Apenas screenshot do portal BH; PDF/XML da nota nao foi baixado"
            if filled
            else "Shadow DOM renderizado mas nenhum campo encontrado; PDF/XML da nota nao foi baixado"
        )
        return DownloadResult(success=False, file_path=str(screenshot) if screenshot else None, error=msg)
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
        return DownloadResult(
            success=False,
            file_path=str(screenshot) if screenshot else None,
            error="Apenas screenshot do portal Nota Carioca; cadastro municipal/CCM nao foi baixado",
        )
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
        return DownloadResult(success=False, file_path=str(screenshot) if screenshot else None, error=error_msg)
    except Exception as exc:
        logger.error("RJ invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Barueri — ISSNet Online (stealth context para tentativa de bypass Cloudflare)
# ---------------------------------------------------------------------------

def capture_rj_invoice(row: InputRow, dest_dir: Path) -> DownloadResult:
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright nao instalado")

    cod = row.cod_verificacao.strip()
    referencia = (row.referencia or "").strip()
    if not referencia or not cod:
        return DownloadResult(success=False, error="Nota Carioca exige numero da DSPREST e codigo de verificacao")

    try:
        from src.services.captcha_solver import solve

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            logger.info("RJ: acessando Nota Carioca para nota {} (cod {})", row.id_documento, cod)
            last_error = "Nota Carioca nao retornou a DSPREST"

            for attempt in range(3):
                resp = page.goto(_RJ_VERIFICACAO_URL, timeout=30000, wait_until="networkidle")
                if resp and resp.status >= 400:
                    browser.close()
                    return DownloadResult(
                        success=False,
                        error=f"Nota Carioca retornou HTTP {resp.status} - portal indisponivel",
                    )

                for selector, value in [
                    ("input[name='ctl00$cphCabMenu$tbCPFCNPJ']", row.cnpj),
                    ("input[name='ctl00$cphCabMenu$tbNota']", referencia),
                    ("input[name='ctl00$cphCabMenu$tbVerificacao']", cod),
                ]:
                    page.fill(selector, value, timeout=5000)

                captcha = page.locator("img[src*='CaptchaImage.aspx']").first.screenshot()
                captcha_text = solve(captcha, only_alnum=True)
                if not captcha_text:
                    last_error = "Captcha Nota Carioca nao resolvido"
                    continue

                page.fill("input[name='ctl00$cphCabMenu$ccCodigo$ccCodigo']", captcha_text, timeout=5000)
                page.evaluate(
                    """(value) => {
                        const hidden = document.querySelector(
                            "input[name='ctl00$cphCabMenu$ccCodigo$tbCaptchaControl']"
                        );
                        if (hidden) hidden.value = value;
                    }""",
                    captcha_text,
                )

                try:
                    with page.expect_navigation(wait_until="networkidle", timeout=30000):
                        page.click("input[name='ctl00$cphCabMenu$btVerificar']")
                except Exception:
                    page.wait_for_load_state("networkidle", timeout=15000)

                text = " ".join(page.inner_text("body").split())
                lower = text.lower()
                for marker in (
                    "contribuinte nao encontrado",
                    "contribuinte não encontrado",
                    "documento nao encontrado",
                    "documento não encontrado",
                    "codigo invalido",
                    "código inválido",
                    "informe corretamente",
                ):
                    marker_pos = lower.find(marker)
                    if marker_pos >= 0:
                        start = max(0, marker_pos - 80)
                        last_error = text[start:marker_pos + 220]
                        break
                else:
                    if (
                        "verificacao de autenticidade da dsprest" not in lower
                        and ("prestador de serviços" in lower or "prestador de servicos" in lower)
                        and ("tomador de serviços" in lower or "tomador de servicos" in lower)
                    ):
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        out = dest_dir / f"nota_carioca_{referencia}.pdf"
                        page.pdf(path=str(out), format="A4", print_background=True)
                        browser.close()
                        return DownloadResult(success=True, file_path=str(out))

                    last_error = text[:220] or "Nota Carioca nao exibiu documento oficial"

                logger.info("RJ: Nota Carioca tentativa {} falhou: {}", attempt + 1, last_error)

            browser.close()
        return DownloadResult(success=False, error=f"Nota Carioca sem PDF/XML: {last_error}")
    except Exception as exc:
        logger.error("RJ invoice capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))


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

            file_path = None
            if _SAVE_EVIDENCE:
                try:
                    out = _screenshot(page, dest_dir, filename)
                    file_path = str(out) if out else None
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
    Captura evidência da nota no portal público da NFS-e Nacional.

    Usa a Consulta Pública oficial (`/consultapublica/?tpc=1&chave=...`), que
    aceita a chave na query string e renderiza a página da nota específica —
    evidência muito melhor que a home de login. A consulta final dos dados é
    protegida por hCaptcha; os dados da nota já foram extraídos da chave pelo
    decodificador, então aqui capturamos a página de consulta como comprovante.
    """
    sync_playwright = _try_import_playwright()
    if not sync_playwright:
        return DownloadResult(success=False, error="Playwright não instalado")

    safe_chave = chave.replace(" ", "")
    url_consulta = _NFSE_NACIONAL_CONSULTA.format(key=safe_chave)
    safe_name = safe_chave[:30]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = _stealth_context(browser)
            page = ctx.new_page()
            logger.info(
                "NFS-e Nacional: consulta pública com chave {}... ({})",
                safe_chave[:12], row.id_documento,
            )
            resp = page.goto(url_consulta, timeout=30000, wait_until="domcontentloaded")
            status = resp.status if resp else None
            page.wait_for_timeout(1500)  # deixa o SPA renderizar o formulário com a chave
            screenshot = _screenshot(page, dest_dir, f"nfse_nacional_{safe_name}")
            browser.close()

        error = None
        if not status or status >= 400:
            error = f"Consulta pública NFS-e retornou HTTP {status}"
        if status == 200 and not error:
            error = "Consulta publica capturada em screenshot; PDF/XML da nota nao foi baixado"
        return DownloadResult(success=False, file_path=str(screenshot) if screenshot else None, error=error)
    except Exception as exc:
        logger.error("NFS-e Nacional capture error: {}", exc)
        return DownloadResult(success=False, error=str(exc))
