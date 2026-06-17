# Analise inicial - POC de automacao CCM + download de documentos

## Resumo executivo

A POC deve ser tratada como uma automacao fiscal orientada por municipios. A planilha de entrada traz 25 linhas, distribuidas igualmente entre 5 municipios: Belo Horizonte, Rio de Janeiro, Barueri, Porto Alegre e Nova Lima. O campo `CCM` esta vazio em todas as linhas, e o campo operacional mais importante para consulta de nota e `COD.VERIFICACAO`, que aparece em formatos distintos por municipio e por origem da nota.

Minha recomendacao e comecar por um backend em Python para orquestracao, leitura/escrita do Excel, normalizacao de CNPJ/codigos, logging e persistencia; e usar Node.js com Playwright para automacoes web onde nao houver API publica estavel. Essa divisao deixa Python forte no pipeline de dados e Node.js forte na navegacao real dos portais municipais.

## O que as instrucoes pedem

Para cada linha da planilha:

- identificar municipio, fornecedor, CNPJ e dados de consulta da nota;
- escolher a estrategia por municipio;
- consultar CCM ou inscricao municipal;
- baixar cadastro municipal da empresa, quando disponivel;
- baixar documento da nota fiscal em PDF/XML;
- salvar evidencias em pastas organizadas;
- atualizar a planilha com status, mensagens tecnicas e caminhos dos arquivos.

Entrega esperada:

- repositorio GitHub publico;
- ou pasta compactada com implementacao;
- documentacao das decisoes tecnicas, desafios e solucoes.

## Leitura da planilha

Arquivo analisado: `C:\Users\CEPEDII\Downloads\janabril2026_amostra_5x5.xlsx`

Aba: `Amostra_5x5`

Dimensao: 25 registros de dados, 18 colunas.

Colunas relevantes:

- `ID do documento`
- `Empresa`
- `Nº documento`
- `Fornecedor`
- `Nome fornecedor`
- `CNPJ`
- `CCM`
- `Referência`
- `MUNICIPIO`
- `COD.VERIFICACAO`

Distribuicao por municipio:

- Belo Horizonte: 5 linhas
- Rio de Janeiro: 5 linhas
- Barueri: 5 linhas
- Porto Alegre: 5 linhas
- Nova Lima: 5 linhas

Observacoes importantes:

- `CCM` esta vazio em 25 de 25 linhas.
- `Nº documento` so esta preenchido em 5 linhas; nao pode ser usado como chave obrigatoria.
- `COD.VERIFICACAO` esta preenchido em todas as linhas, mas mistura chave numerica longa, codigo alfanumerico simples, codigo com hifen e codigo com pontos.
- Ha fornecedores duplicados por CNPJ em alguns municipios; convem cachear consultas de CCM por `municipio + CNPJ`.

## Estrategia tecnica recomendada

### Stack principal

Python:

- `pandas` ou `openpyxl` para leitura e atualizacao da planilha.
- `pydantic` para validar e normalizar linhas de entrada.
- `httpx` para chamadas HTTP/API.
- `tenacity` para retry com backoff.
- `structlog` ou `loguru` para logs estruturados.
- `pytest` para testes de normalizacao e conectores.
- `typer` para CLI simples.

Node.js:

- `Playwright` para navegacao, download de PDF/XML, screenshots e tratamento de portais sem API.
- `zod` para validar payloads/configuracoes, se criarmos runners Node isolados.
- scripts chamados pelo Python via subprocesso, ou um pequeno worker HTTP/local quando a POC crescer.

Armazenamento:

- SQLite para rastrear execucoes, cache de CCM por CNPJ/municipio e status de downloads.
- Sistema de arquivos para evidencias.

Empacotamento:

- `uv` para ambiente Python.
- `pnpm` ou `npm` para dependencias Node.js.
- Docker opcional, especialmente util para Playwright e reproducibilidade.

### Arquitetura sugerida

```text
input.xlsx
   |
   v
Python CLI
   |
   +-- valida e normaliza linhas
   +-- resolve estrategia por municipio
   +-- consulta cache SQLite
   +-- chama conector API ou navegador
   +-- grava evidencias em output/
   +-- atualiza planilha final
   |
   v
output/
   +-- resultado.xlsx
   +-- logs/execution.jsonl
   +-- evidencias/
       +-- BELO_HORIZONTE/
       +-- RIO_DE_JANEIRO/
       +-- BARUERI/
       +-- PORTO_ALEGRE/
       +-- NOVA_LIMA/
```

### Padrao de conectores

Cada municipio deve ter um conector com a mesma interface:

```python
class MunicipalConnector:
    def lookup_ccm(self, row) -> CcmResult: ...
    def download_company_registration(self, row) -> DownloadResult: ...
    def download_invoice(self, row) -> DownloadResult: ...
```

Isso evita espalhar regras especificas dos portais pelo pipeline principal.

## Estrategia por municipio

Belo Horizonte:

- Ha portal BHISS Digital para consulta de autenticidade de NFS-e.
- Deve ser tratado inicialmente por Playwright, com possibilidade de HTTP direto se o fluxo JSF permitir.

Rio de Janeiro:

- A partir de janeiro de 2026, a prefeitura indica migracao da emissao para o Emissor Nacional de NFS-e, mantendo sistemas anteriores para consulta de competencias antigas.
- Como a amostra e janeiro a abril de 2026, a estrategia deve priorizar NFS-e Nacional para notas novas e manter fallback para Nota Carioca/consulta municipal quando o codigo indicar legado.

Barueri:

- Portal municipal possui verificacao de autenticidade e web services de consulta.
- Deve ser um dos primeiros municipios para automatizar, pois o codigo com pontos/hifen da amostra parece bater com o formato documentado no proprio portal.

Porto Alegre:

- Portal municipal de NFS-e possui consulta publica e exibicao de NFS-e.
- Provavel automacao via Playwright/HTTP em paginas JSF.

Nova Lima:

- A prefeitura comunicou adesao ao padrao nacional de NFS-e a partir de 01/01/2026.
- Como a amostra e de 2026, deve priorizar NFS-e Nacional, com fallback para portal antigo apenas se necessario.

## Modelo de saida recomendado na planilha

Adicionar colunas ao final:

- `STATUS_EXECUCAO`
- `MENSAGEM_TECNICA`
- `CCM_ENCONTRADO`
- `ARQUIVO_CADASTRO`
- `ARQUIVO_NOTA_PDF`
- `ARQUIVO_NOTA_XML`
- `MUNICIPIO_ESTRATEGIA`
- `DATA_EXECUCAO`

## Primeira implementacao recomendada

1. Criar scaffold do projeto com Python + Node.js.
2. Implementar leitura, normalizacao e escrita do Excel.
3. Criar cache SQLite e estrutura de pastas de evidencia.
4. Implementar conectores "stub" para os 5 municipios, retornando status controlado.
5. Implementar primeiro municipio real: Barueri ou Belo Horizonte.
6. Adicionar Playwright com captura de screenshot e download.
7. Implementar NFS-e Nacional para chaves numericas longas, priorizando Rio de Janeiro e Nova Lima.
8. Fechar README com como rodar, decisoes tecnicas e limitacoes conhecidas.

## Riscos principais

- Captcha em portais municipais.
- Mudanca de layout em paginas JSF/ASP.NET.
- Portais com sessao, timeout ou bloqueio por volume.
- Necessidade de campos que nao existem na planilha, como valor da nota ou CNPJ do tomador em alguns municipios.
- Diferenca entre cadastro municipal da empresa e consulta de autenticidade de nota.
- Regras de 2026 mudando por municipio com a NFS-e Nacional.

## Arquitetura com tela web

Para causar melhor impressao, a POC deve ser apresentada como um sistema web, nao apenas como um script de terminal. A automacao continua existindo por baixo, mas o usuario interage por uma tela.

Fluxo proposto:

```text
Usuario
   |
   v
Tela Web
   |
   +-- upload da planilha
   +-- botao "Iniciar processamento"
   +-- acompanhamento de status por linha
   +-- download da planilha final
   +-- acesso aos PDFs/XMLs/evidencias
   |
   v
API Backend
   |
   +-- valida planilha
   +-- cria execucao
   +-- dispara automacao
   +-- grava logs, status e arquivos
   |
   v
Workers de automacao
   |
   +-- conectores por municipio
   +-- Playwright para portais sem API
   +-- HTTP/API quando disponivel
```

Stack recomendada para a versao com tela:

- Frontend: Next.js com React e TypeScript.
- UI: Tailwind CSS + shadcn/ui.
- Backend/API: FastAPI em Python.
- Automacao web: Node.js + Playwright.
- Banco local da POC: SQLite.
- Fila simples: processo worker Python com status no banco.
- Excel: pandas/openpyxl.
- Logs: loguru ou structlog.

Telas sugeridas:

- Dashboard de execucoes.
- Upload de planilha.
- Tela de processamento em andamento.
- Tabela de resultados por linha.
- Detalhe da linha com mensagem tecnica, CCM, arquivos e evidencias.
- Pagina de configuracao dos municipios/conectores.

Essa abordagem passa a impressao de produto, mas sem aumentar demais o risco da POC. O sistema pode rodar localmente em dois servicos:

```bash
backend:  http://localhost:8000
frontend: http://localhost:3000
```

Para uma apresentacao, o usuario abre o frontend, envia a planilha, acompanha a execucao e baixa o resultado.

## Decisao recomendada

Comecar com uma POC modular com tela web, nao com automacao monolitica. O primeiro valor rapido vem de provar o pipeline completo em 1 municipio, com status e evidencia gravados, e depois plugar os demais municipios no mesmo contrato.

Minha ordem sugerida:

1. Barueri, por ter portal com verificacao clara por codigo de autenticidade.
2. Belo Horizonte, por volume comum e portal publico BHISS.
3. Nova Lima e Rio de Janeiro via NFS-e Nacional para notas de 2026.
4. Porto Alegre como conector JSF municipal.
