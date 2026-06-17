# POC de Automação - CCM + Download de Documentos NFS-e

Automação fiscal que lê uma planilha de entrada, consulta o **CCM (Inscrição Municipal)** de cada empresa e faz o download dos documentos fiscais (cadastro municipal + nota fiscal) nos portais de 5 municípios brasileiros.

![Demo do pipeline](demo.gif)

---

## O que faz

Para cada linha da planilha:

1. Identifica município, CNPJ e código de verificação da nota
2. Resolve a estratégia correta por município (portal público ou NFS-e Nacional)
3. Consulta CCM — grava se encontrado, registra erro técnico se indisponível
4. Baixa o cadastro municipal da empresa (PDF, XML ou screenshot)
5. Baixa o documento da nota fiscal (PDF, XML ou screenshot)
6. Grava resultado por linha com status, mensagem técnica e caminho dos arquivos
7. Gera planilha de saída colorida e relatório HTML com evidências embutidas

---

## Municípios suportados

| Município | Portal | Estratégia | Limitação |
|---|---|---|---|
| Belo Horizonte | `servicos.pbh.gov.br` | Playwright (Sydle SPA) | Shadow DOM — captura screenshot |
| Rio de Janeiro | Nota Carioca | Playwright + NFS-e Nacional | CAPTCHA bloqueia submissão |
| Barueri | ISSNet Online | Playwright | Cloudflare 403 — evidência .txt |
| Porto Alegre | — | NFS-e Nacional (chave longa) | DNS failure em todos os portais |
| Nova Lima | — | NFS-e Nacional exclusivo | Portal migrado em Jan/2026 |

---

## Resultado da execução real

Executado sobre `janabril2026_amostra_5x5.xlsx` (25 linhas):

| Status | Linhas | Detalhe |
|---|---|---|
|  SUCESSO | 10 | BH (5) + RJ (5) — screenshots capturados |
|  PARCIAL | 9 | POA (4) + Nova Lima (5) — NFS-e Nacional capturado, cadastro offline |
|  ERRO | 6 | Barueri (5) Cloudflare + POA código curto (1) portal offline |

---

## Como rodar

### Python local

```bash
pip install -e ".[dev]"
python -m playwright install chromium
python -m src.main input/janabril2026_amostra_5x5.xlsx
```

### Docker

```bash
docker compose run --rm pipeline
```

---

## Saídas geradas

```
output/
├── resultado_<timestamp>.xlsx       # planilha com 9 colunas de resultado
├── relatorio_<timestamp>.html       # relatório HTML com screenshots embutidos
└── evidencias/
    └── <MUNICIPIO>/
        └── <CNPJ>/
            ├── cadastro_<CNPJ>.png
            └── notas/
                └── nota_<cod>.png
```

### Colunas adicionadas na planilha

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

---

## Arquitetura

```
input.xlsx
    │
    ▼
CLI (typer)
    │
    ▼
Pipeline (rich live table)
    │
    ├── Pydantic — valida e normaliza cada linha
    ├── SQLite  — cache de CCM por municipio::cnpj
    │
    └── MunicipalConnector (Strategy Pattern)
            ├── BeloHorizonteConnector
            ├── RioDeJaneiroConnector
            ├── BarueriConnector
            ├── PortoAlegreConnector
            └── NovaLimaConnector
                    │
                    └── Playwright (headless Chromium)
                            └── screenshots como evidência
    │
    ▼
output/
    ├── resultado.xlsx
    ├── relatorio.html
    └── evidencias/
```

---

## Testes

```bash
python -m pytest tests/ -v
```

14 testes cobrindo: normalização CNPJ, detecção de chave NFS-e Nacional, validação de modelos Pydantic, leitura do xlsx (25 linhas, 5 municípios, unicidade de cache key).

---

## Decisões técnicas

Ver [`docs/decisoes-tecnicas.md`](docs/decisoes-tecnicas.md) para detalhamento de:
- Verificação de URLs por HTTP antes de implementar
- Decisão por município (BH Sydle SPA, RJ CAPTCHA, Barueri Cloudflare, etc.)
- Rationale do cache SQLite e Strategy Pattern
- Tratamento de timeout e limitações conhecidas
