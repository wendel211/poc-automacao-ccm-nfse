# Decisões Técnicas - POC CCM + NFS-e

## Stack escolhida

**Python** como linguagem principal.

- `pandas` / `openpyxl` — leitura e escrita do Excel
- `pydantic` v2 — validação e normalização de cada linha da planilha antes de qualquer I/O
- `httpx` — requisições HTTP com suporte a async e redirects
- `tenacity` — retry com backoff exponencial em conectores instáveis
- `loguru` — logs estruturados com nível e contexto por linha
- `playwright` — automação de navegador headless (Chromium) para portais sem API
- `rich` — tabela ao vivo no terminal mostrando progresso por linha
- `typer` — CLI com `--help` gerado automaticamente
- SQLite — cache de CCM por `municipio::cnpj` para evitar consultas duplicadas

## Padrão de conectores (Strategy Pattern)

Cada município implementa a mesma interface:

```python
class MunicipalConnector:
    def lookup_ccm(self, row: InputRow) -> CcmResult: ...
    def download_company_registration(self, row: InputRow, dest: Path) -> DownloadResult: ...
    def download_invoice(self, row: InputRow, dest: Path) -> DownloadResult: ...
```

O pipeline principal não sabe qual portal está acessando — apenas chama o conector correto pelo município. Isso permite adicionar novos municípios sem tocar no orquestrador.

## Detecção de chave NFS-e Nacional vs. código municipal

A planilha mistura dois formatos em `COD.VERIFICACAO`:

- **Chave longa (40+ dígitos numéricos)**: padrão NFS-e Nacional (ABRASF). Pode vir com espaços de agrupamento.
- **Código curto alfanumérico**: proprietário de cada portal municipal.

A função `is_nfse_nacional_key()` faz esse roteamento via regex `\d{40,}` após remover espaços. Isso evita que o conector errado tente processar uma chave que não reconhece.

## Verificação de URLs antes de implementar

Antes de escrever qualquer automação, todos os endpoints foram verificados via `httpx`. Resultado:

| Município | URL testada | Resultado |
|---|---|---|
| Belo Horizonte | `bhiss.pbh.gov.br` | DNS failure |
| Belo Horizonte | `servicos.pbh.gov.br/nfse/autenticidade` | **200 OK** |
| Barueri | `barueri.nfse.ig.com.br` | DNS failure |
| Barueri | `issnetonline.com.br/webissnetonline/velo/autenticidade.jsf?id=12` | **403 Cloudflare** |
| Porto Alegre | todos os candidatos testados | DNS failure |
| Nova Lima | todos os candidatos testados | DNS failure |
| NFS-e Nacional | `/Visualizar?chaveAcesso=` | **HTTP 500** (requer sessão) |

Esse mapeamento evitou implementar automações em URLs erradas e permitiu documentar limitações reais antes de escrever código.

## Decisões por município

### Belo Horizonte
Portal `servicos.pbh.gov.br/nfse/autenticidade` retorna 200. Usa Sydle SPA com Web Components (Shadow DOM) — o formulário não renderiza sem JavaScript executado. Playwright navega ao portal e captura screenshot como evidência.

### Rio de Janeiro
Nota Carioca `/documentos/verificacao.aspx` é um formulário ASP.NET WebForms. O Playwright preenche os campos `tbCPFCNPJ`, `tbNota` e `tbVerificacao` mas um CAPTCHA (`tbCaptchaControl`) bloqueia a submissão. Screenshot do formulário preenchido é salvo como evidência. Chaves longas são roteadas para NFS-e Nacional.

### Barueri
ISSNet Online retorna HTTP 403 via Cloudflare para qualquer client headless. A CSP do Cloudflare também bloqueia `Page.captureScreenshot` via CDP. Solução: salvar arquivo `.txt` com URL, status HTTP e descrição do bloqueio como evidência da tentativa.

### Porto Alegre
Todos os endpoints testados retornam NXDOMAIN. Chaves longas são roteadas para NFS-e Nacional. Códigos curtos registram INDISPONIVEL com mensagem descritiva.

### Nova Lima
Município aderiu ao NFS-e Nacional em 01/01/2026. Portal municipal offline. Todas as notas da amostra (jan-abr/2026) são roteadas para NFS-e Nacional.

### NFS-e Nacional
Endpoint HTTP `/Visualizar?chaveAcesso=` retorna 500 sem sessão autenticada. Playwright navega ao portal `nfse.gov.br/EmissorNacional/` e captura screenshot da página de login como evidência. Autenticação é via gov.br — não automatizável sem credenciais.

## Cache SQLite

Fornecedores aparecem duplicados na planilha com mesmo CNPJ e mesmo município. Sem cache, faríamos consultas idênticas ao portal para cada linha. O SQLite garante que a segunda linha reutilize o resultado da primeira, com chave `municipio::cnpj`.

## Tratamento de timeout e layout

Todos os conectores usam `tenacity` com `stop_after_attempt(3)` e `wait_exponential`. O Playwright usa `wait_until="domcontentloaded"` em vez de `networkidle` — portais com analytics e CDN externos nunca atingem `networkidle` dentro de 30s, gerando falsos erros de navegação.

## Saídas geradas

Por execução:
- `output/resultado_<timestamp>.xlsx` — planilha com 9 colunas de resultado coloridas por status
- `output/relatorio_<timestamp>.html` — relatório HTML com cards de resumo e screenshots embutidos em base64
- `output/evidencias/<MUNICIPIO>/<CNPJ>/` — screenshot de cadastro
- `output/evidencias/<MUNICIPIO>/<CNPJ>/notas/` — screenshot ou PDF da nota

## Log de auditoria JSONL

Cada execução grava `output/logs/execution_<timestamp>.jsonl` com uma entrada JSON por linha processada. Campos: `id_documento`, `municipio`, `cnpj`, `status`, `mensagem_tecnica`, `ccm_encontrado`, caminhos de arquivos e `municipio_estrategia`.

Complementa o SQLite (que persiste cache entre execuções) e o relatório HTML (visualização): o JSONL é ideal para ingestão em ferramentas de análise e auditoria de execuções individuais. Arquivos `.jsonl` são ignorados pelo `.gitignore` por serem artefatos gerados.

## CI com GitHub Actions

O workflow `.github/workflows/ci.yml` roda `pytest tests/ -v` em todo push e pull request. Configuração: Ubuntu latest, Python 3.11, cache de pip.

Os testes unitários (14 casos cobrindo normalização de CNPJ, detecção de chave NFS-e Nacional, modelos Pydantic e leitura do Excel) não dependem de Playwright nem de portais externos, portanto executam sem configuração adicional no runner. Testes de integração com browser são excluídos do CI por exigirem credenciais e portais reais.

## Limitações conhecidas e justificativas

| Limitação | Causa | Como foi tratado |
|---|---|---|
| CCM não encontrado em nenhum município | Nenhum portal expõe CCM sem autenticação | Registrado como INDISPONIVEL com mensagem técnica |
| CAPTCHA no RJ | Nota Carioca exige resolução manual | Formulário preenchido + screenshot como evidência |
| Cloudflare 403 em Barueri | ISSNet bloqueia headless browsers | Arquivo .txt com status HTTP como evidência |
| NFS-e Nacional requer login gov.br | Portal não tem endpoint público sem sessão | Screenshot da página de login como evidência |
| Portais POA e Nova Lima offline | DNS failure em todos os endpoints | INDISPONIVEL documentado; chaves longas via NFS-e Nacional |
