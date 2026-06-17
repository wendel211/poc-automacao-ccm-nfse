# poc-automacao-ccm-nfse

POC de automação fiscal: consulta de **CCM (Inscrição Municipal)** e download de documentos NFS-e para 5 municípios brasileiros, a partir de planilha de entrada.

![Demo do pipeline](demo.gif)

## O que faz

Para cada linha da planilha de entrada:

1. Identifica município, CNPJ e código de verificação da nota
2. Consulta CCM/Inscrição Municipal da empresa no portal do município
3. Baixa o cadastro municipal da empresa (PDF, XML ou screenshot)
4. Baixa o documento da nota fiscal (PDF, XML ou screenshot)
5. Atualiza a planilha com status, CCM encontrado e caminhos dos arquivos
6. Gera relatório HTML com screenshots embutidos

## Municípios suportados

| Município | Estratégia | Limitação documentada |
|---|---|---|
| Belo Horizonte | `servicos.pbh.gov.br` (Playwright) + NFS-e Nacional | Sydle SPA / Shadow DOM |
| Rio de Janeiro | Nota Carioca (formulário preenchido) + NFS-e Nacional | CAPTCHA bloqueia submissão |
| Barueri | ISSNet Online (Playwright) | Cloudflare 403 — evidência txt |
| Porto Alegre | NFS-e Nacional (chave longa) / INDISPONIVEL (código curto) | DNS fail em todos os portais |
| Nova Lima | NFS-e Nacional exclusivo (adesão jan/2026) | Portal municipal offline |

## Como rodar

### Opção 1 — Python local

```bash
pip install -e ".[dev]"
python -m playwright install chromium
python -m src.main input/janabril2026_amostra_5x5.xlsx
```

### Opção 2 — Docker

```bash
docker compose run --rm pipeline
```

Durante a execução o terminal exibe uma tabela ao vivo com o status de cada linha:

```
  POC Automacao CCM + NFS-e
 ┏━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━┓
 ┃ #  ┃ ID      ┃ Município        ┃ CNPJ              ┃ Status       ┃ Evidenc ┃
 ┡━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━┩
 │ 1  │ 2652712 │ Belo Horizonte   │ 28.203.865/0001…  │ [OK] SUCESSO │ sim     │
 │ 2  │ 2586757 │ Belo Horizonte   │ 09.346.601/0021…  │ [OK] SUCESSO │ sim     │
 │ 3  │ 2716126 │ Rio De Janeiro   │ 13.952.675/0001…  │ [OK] SUCESSO │ sim     │
 │ …  │ …       │ …                │ …                 │ ⏳ processando│ …       │
 └────┴─────────┴──────────────────┴───────────────────┴──────────────┴─────────┘
```

Ao final gera automaticamente:
- `output/resultado_<timestamp>.xlsx` — planilha com 9 colunas de resultado, coloridas por status
- `output/relatorio_<timestamp>.html` — relatório com cards de resumo e screenshots embutidos
- `output/evidencias/<MUNICIPIO>/<CNPJ>/` — screenshots e arquivos de evidência

### Testes

```bash
python -m pytest tests/ -v
```

## Estrutura do projeto

```
.
├── src/
│   ├── main.py               # CLI (typer)
│   ├── pipeline.py           # Orquestrador + tabela rich ao vivo
│   ├── report.py             # Gerador de relatório HTML
│   ├── models.py             # Modelos Pydantic (InputRow, RowResult, ...)
│   ├── excel_handler.py      # Leitura e escrita do .xlsx
│   ├── database.py           # Cache SQLite (CCM por município+CNPJ)
│   ├── connectors/           # Um conector por município (Strategy pattern)
│   │   ├── base.py
│   │   ├── barueri.py
│   │   ├── belo_horizonte.py
│   │   ├── rio_de_janeiro.py
│   │   ├── porto_alegre.py
│   │   ├── nova_lima.py
│   │   └── nfse_acional.py
│   ├── browser/
│   │   └── playwright_runner.py
│   └── utils/
│       ├── cnpj.py
│       └── filesystem.py
├── tests/                    # 14 testes unitários (pytest)
├── input/                    # Planilha de entrada
├── output/                   # Resultados gerados (xlsx, html, evidências)
├── docs/                     # Decisões técnicas e análise de portais
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Saída da planilha

Colunas adicionadas ao final (color-coded por status):

| Coluna | Descrição |
|---|---|
| `STATUS_EXECUCAO` | SUCESSO / PARCIAL / ERRO / INDISPONIVEL |
| `MENSAGEM_TECNICA` | Detalhe do erro (timeout, captcha, HTTP status) |
| `CCM_ENCONTRADO` | Inscrição Municipal encontrada |
| `ARQUIVO_CADASTRO` | Caminho do cadastro municipal |
| `ARQUIVO_NOTA_PDF` | Caminho do PDF da nota |
| `ARQUIVO_NOTA_XML` | Caminho do XML da nota |
| `ARQUIVO_EVIDENCIA` | Screenshot PNG de evidência |
| `MUNICIPIO_ESTRATEGIA` | Estratégia usada por município |
| `DATA_EXECUCAO` | Timestamp da execução |

## Resultado da execução real

Executado sobre `janabril2026_amostra_5x5.xlsx` (25 linhas, 5 municípios):

| Status | Linhas | Motivo |
|---|---|---|
| SUCESSO | 10 | BH (5) + RJ (5) — screenshots capturados |
| PARCIAL | 9 | POA (4) + Nova Lima (5) — NFS-e Nacional capturado, cadastro municipal offline |
| ERRO | 6 | Barueri (5) Cloudflare 403 + POA código curto (1) portal offline |

Evidências em `output/evidencias/` — 34 arquivos organizados por município e CNPJ.

## Limitações conhecidas

- **CAPTCHA (RJ):** formulário preenchido mas submissão bloqueada — screenshot como evidência
- **Cloudflare (Barueri):** ISSNet retorna 403 para qualquer client headless — evidência .txt
- **Auth gov.br (NFS-e Nacional):** portal exige login — screenshot da página de login
- **CCM não público:** nenhum dos 5 municípios expõe CCM sem autenticação
- **Portais offline (POA / Nova Lima):** DNS fail em todos os endpoints testados
