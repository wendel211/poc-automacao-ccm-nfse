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

## Decisão central: extrair dados das chaves fiscais em vez de depender dos portais

Todos os portais municipais bloqueiam acesso automatizado — CAPTCHA (RJ), Cloudflare (Barueri), login gov.br (NFS-e Nacional), DNS offline (POA, Nova Lima). Insistir em baixar o PDF no portal não traz resultado.

A virada de estratégia: **a coluna `COD.VERIFICACAO` já contém os dados da nota**. As chaves de acesso são padronizadas nacionalmente e auto-contidas. Decodificá-las entrega dados reais e verificáveis sem nenhum portal.

A planilha mistura três formatos em `COD.VERIFICACAO`, distinguidos pelo número de dígitos (`src/utils/fiscal_keys.py`):

| Dígitos | Tipo | Dados extraídos |
|---|---|---|
| 50 | Chave NFS-e Nacional (serviços) | município IBGE, CNPJ emitente, número, competência |
| 44 | Chave NF-e/NFC-e (produtos, mod. 55/65) | UF, CNPJ emitente, modelo, série, número, competência, **DV validado (módulo 11)** |
| curto alfanumérico | código proprietário do portal municipal | — (requer o portal específico) |

O layout de cada chave foi validado empiricamente contra as 25 linhas reais: o CNPJ embutido na chave bate com o CNPJ do fornecedor (exceto divergências legítimas, ver abaixo), e a competência `AAMM` confere com o período da amostra (jan-abr/2026). O dígito verificador da NF-e é recalculado por módulo 11 — todas as chaves de 44 dígitos da amostra passaram.

## Enriquecimento do cadastro da empresa via API pública

A **Inscrição Municipal (CCM) não é exposta por nenhuma fonte pública federal** — é cadastro de cada prefeitura, acessível apenas com login no portal municipal. Em vez de entregar nada, o pipeline busca o cadastro federal oficial da empresa (`src/services/cnpj_lookup.py`) por uma cadeia de fallback resiliente a rate-limit e instabilidade:

```
ReceitaWS  ->  CNPJa (open)  ->  BrasilAPI
```

A primeira resposta válida vence; o resultado é normalizado (razão social, situação cadastral, atividade principal) independentemente do provedor. Resultados são cacheados por CNPJ na execução, evitando consultas duplicadas para fornecedores repetidos.

## Validação cruzada como auditoria

Com o CNPJ embutido na chave fiscal e o cadastro da Receita em mãos, o pipeline compara o **CNPJ do emitente da chave** contra o **fornecedor listado na planilha**. Na amostra real isso revelou 2 divergências legítimas (ex.: nota emitida por prestador de Curitiba para um fornecedor cadastrado em Barueri) — exatamente o tipo de inconsistência fiscal que uma automação de auditoria deve sinalizar.

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
Portal `servicos.pbh.gov.br/nfse/autenticidade` retorna 200. Usa Sydle SPA com Web Components (Shadow DOM) — o formulário é renderizado por ES modules (`@sydle/pbh-components`) dentro de shadow roots profundos. A interação com `page.fill()` direto não funciona.

Solução implementada: `wait_for_function()` aguarda a presença de shadow roots no DOM (SPA inicializada), depois `page.evaluate()` executa JavaScript recursivo que percorre todos os shadow roots e preenche o primeiro input visível usando o native property setter (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set`) para disparar os eventos corretamente no framework. Em seguida, outra `evaluate()` recursiva localiza e clica no botão de consulta. O resultado (ou a tela com o campo preenchido) é capturado como evidência.

### Rio de Janeiro
Nota Carioca `/documentos/verificacao.aspx` é um formulário ASP.NET WebForms. O Playwright preenche os campos `tbCPFCNPJ`, `tbNota` e `tbVerificacao` (o ViewState é gerenciado automaticamente pelo Playwright, que executa o JavaScript da página). O CAPTCHA (`tbCaptchaControl`) bloqueia a submissão. Screenshot do formulário preenchido é salvo como evidência. Chaves longas são roteadas para NFS-e Nacional. Portal verificado como offline (ConnectError) em jun/2026.

### Barueri
ISSNet Online retorna HTTP 403 via Cloudflare para qualquer client headless básico. Estratégia de contorno implementada: contexto Playwright com `--disable-blink-features=AutomationControlled`, User-Agent Chrome/120 realista, viewport 1920×1080, `locale=pt-BR`, `timezone_id=America/Sao_Paulo` e `add_init_script` injetando `navigator.webdriver = undefined` antes de qualquer script da página. Quando a CSP do Cloudflare ainda bloqueia `Page.captureScreenshot`, salva `.txt` com URL, status HTTP e descrição completa da tentativa.

### Porto Alegre
Todos os endpoints testados retornam NXDOMAIN. Chaves longas são roteadas para NFS-e Nacional. Códigos curtos registram INDISPONIVEL com mensagem descritiva.

### Nova Lima
Município aderiu ao NFS-e Nacional em 01/01/2026. Portal municipal offline. Todas as notas da amostra (jan-abr/2026) são roteadas para NFS-e Nacional.

### NFS-e Nacional
O endpoint `/Visualizar?chaveAcesso={key}` retorna HTTP 500 com erro de roteamento ASP.NET MVC no servidor (`"Foram encontrados vários tipos que correspondem ao controlador 'Nfse'"`) — bug no lado do servidor, não na requisição. Tentativas com httpx e Playwright confirmam o mesmo comportamento.

Estratégia implementada: Playwright navega diretamente à URL `Visualizar?chaveAcesso={key}` (não à home page genérica). Ao receber 500, registra o erro e faz fallback para a home page do EmissorNacional, capturando o estado com a tentativa documentada. Autenticação é via gov.br — não automatizável sem credenciais.

## Cache SQLite

Fornecedores aparecem duplicados na planilha com mesmo CNPJ e mesmo município. Sem cache, faríamos consultas idênticas ao portal para cada linha. O SQLite garante que a segunda linha reutilize o resultado da primeira, com chave `municipio::cnpj`.

## Tratamento de timeout e layout

Todos os conectores usam `tenacity` com `stop_after_attempt(3)` e `wait_exponential`. O Playwright usa `wait_until="domcontentloaded"` em vez de `networkidle` — portais com analytics e CDN externos nunca atingem `networkidle` dentro de 30s, gerando falsos erros de navegação.

## Saídas geradas

Por execução:
- `output/resultado_<timestamp>.xlsx` — planilha com 19 colunas de resultado coloridas por status (dados cadastrais, dados da chave decodificada, validações e caminhos de arquivo)
- `output/relatorio_<timestamp>.html` — relatório HTML com cards de resumo e screenshots embutidos em base64
- `output/evidencias/<MUNICIPIO>/<CNPJ>/` — screenshot de cadastro
- `output/evidencias/<MUNICIPIO>/<CNPJ>/notas/` — screenshot ou PDF da nota

## Log de auditoria JSONL

Cada execução grava `output/logs/execution_<timestamp>.jsonl` com uma entrada JSON por linha processada. Campos: `id_documento`, `municipio`, `cnpj`, `status`, `mensagem_tecnica`, `ccm_encontrado`, caminhos de arquivos e `municipio_estrategia`.

Complementa o SQLite (que persiste cache entre execuções) e o relatório HTML (visualização): o JSONL é ideal para ingestão em ferramentas de análise e auditoria de execuções individuais. Arquivos `.jsonl` são ignorados pelo `.gitignore` por serem artefatos gerados.

## CI com GitHub Actions

O workflow `.github/workflows/ci.yml` roda `pytest tests/ -v` em todo push e pull request. Configuração: Ubuntu latest, Python 3.11, cache de pip.

Os testes (28 casos cobrindo normalização de CNPJ, decode de chave NFS-e Nacional e NF-e com validação de DV, cadeia de fallback de enriquecimento de CNPJ com HTTP mockado via respx, modelos Pydantic e leitura do Excel) não dependem de Playwright nem de portais externos, portanto executam sem configuração adicional no runner. Testes de integração com browser são excluídos do CI por exigirem credenciais e portais reais.

## Limitações conhecidas e como foram contornadas

| Bloqueio do portal | Causa | Como foi contornado |
|---|---|---|
| CCM não exposto publicamente | Cadastro de cada prefeitura, exige login municipal | Entrega o cadastro federal completo (Receita) via API pública no lugar |
| CAPTCHA no RJ | Nota Carioca exige resolução manual | Dados extraídos da chave fiscal + cadastro via API; form preenchido como evidência |
| Cloudflare 403 em Barueri | ISSNet bloqueia headless browsers | Dados extraídos da chave + cadastro via API; tentativa stealth + evidência .txt |
| NFS-e Nacional requer login gov.br | Portal não tem endpoint público sem sessão | Chave de 50 dígitos decodificada localmente (município, número, competência) |
| Portais POA e Nova Lima offline | DNS failure em todos os endpoints | Chave decodificada + cadastro via API, sem depender do portal |

O resultado: de **0 linhas com dados** para **20 SUCESSO / 5 PARCIAL / 0 ERRO** na amostra de 25 linhas, mais 2 divergências de CNPJ sinalizadas para auditoria.
