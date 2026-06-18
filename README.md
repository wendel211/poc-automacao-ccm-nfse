# POC de Automação - CCM + Download de Documentos NFS-e

Automação fiscal que lê uma planilha de entrada, consulta o **CCM (Inscrição Municipal)** de cada empresa e faz o download dos documentos fiscais (cadastro municipal + nota fiscal) nos portais de 5 municípios brasileiros.

![Demo do pipeline](demo.gif)

---

## O que faz

Para cada linha da planilha:

1. Identifica município, CNPJ e código de verificação da nota
2. **Decodifica a chave fiscal** (NFS-e Nacional de 50 dígitos ou NF-e/NFC-e de 44 dígitos): extrai município, número, série, competência e CNPJ do emitente — com validação do dígito verificador (módulo 11)
3. **Enriquece o cadastro da empresa** via API pública (cadeia de fallback ReceitaWS → CNPJa → BrasilAPI): razão social, situação cadastral, atividade principal
4. **Valida o CNPJ do emitente** da chave contra o fornecedor da planilha — sinaliza divergências (auditoria)
5. Consulta CCM e captura evidência nos portais municipais (screenshot quando o portal permite)
6. Grava resultado por linha com status, dados extraídos e caminho dos arquivos
7. Gera planilha de saída colorida e relatório HTML com evidências embutidas

> **Como os portais municipais bloqueiam acesso automatizado** (CAPTCHA, Cloudflare, login gov.br, DNS offline), a estratégia que de fato traz resultados é **decodificar as chaves fiscais** — que são auto-contidas e padronizadas nacionalmente — e **enriquecer os dados cadastrais por APIs públicas**. Isso entrega dados reais e verificáveis mesmo sem conseguir baixar o PDF no portal.

---

## Municípios suportados

| Município | Portal | Estratégia de contorno | Bloqueio do portal |
|---|---|---|---|
| Belo Horizonte | `servicos.pbh.gov.br` | Decode da chave + enriquecimento CNPJ; Playwright com Shadow DOM piercing | Sydle SPA / Shadow DOM |
| Rio de Janeiro | Nota Carioca | Decode da chave + enriquecimento CNPJ; form WebForms preenchido | CAPTCHA |
| Barueri | ISSNet Online | Decode da chave + enriquecimento CNPJ; contexto stealth | Cloudflare 403 |
| Porto Alegre | NFS-e Nacional | Decode da chave + enriquecimento CNPJ | DNS failure |
| Nova Lima | NFS-e Nacional | Decode da chave + enriquecimento CNPJ | Portal migrado em Jan/2026 |

---

## Resultado da execução real

Executado sobre `janabril2026_amostra_5x5.xlsx` (25 linhas):

| Status | Linhas | Detalhe |
|---|---|---|
| SUCESSO | 20 | Cadastro da empresa obtido + documento fiscal decodificado/capturado |
| PARCIAL | 5 | Cadastro obtido, mas código é proprietário do portal municipal (não decodificável) e portal bloqueou captura |
| ERRO | 0 | — |

Além disso, a validação cruzada CNPJ-emitente sinalizou **2 divergências reais**: notas cujo CNPJ emitente na chave difere do fornecedor listado na planilha (uma emitida de Curitiba para um fornecedor de Barueri).

> **CCM/Inscrição Municipal**: não é exposta por nenhuma fonte pública federal — é cadastro de cada prefeitura, acessível apenas com autenticação no portal municipal. O pipeline registra a tentativa e entrega, no lugar, o cadastro federal completo da empresa.

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
| `MENSAGEM_TECNICA` | Dados extraídos e/ou detalhe do bloqueio do portal |
| `CCM_ENCONTRADO` | Inscrição Municipal (quando disponível) |
| `RAZAO_SOCIAL` | Razão social da empresa (Receita Federal) |
| `SITUACAO_CADASTRAL` | Situação na Receita (ATIVA, etc.) |
| `ATIVIDADE_PRINCIPAL` | CNAE principal |
| `FONTE_CADASTRO` | Provedor que retornou o cadastro (ReceitaWS/CNPJa/BrasilAPI) |
| `TIPO_DOCUMENTO` | NFSE_NACIONAL / NFE / MUNICIPAL_CURTO |
| `NOTA_MUNICIPIO` | Município (NFS-e) ou UF (NF-e) emissor, extraído da chave |
| `NOTA_NUMERO` | Número da nota extraído da chave |
| `NOTA_COMPETENCIA` | Competência (AAAA-MM) extraída da chave |
| `CNPJ_EMITENTE_CONFERE` | OK / DIVERGE — validação do CNPJ da chave vs. fornecedor |
| `CHAVE_DV_VALIDO` | Validação do dígito verificador (NF-e, módulo 11) |
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
    ├── Pydantic        — valida e normaliza cada linha
    ├── fiscal_keys     — decodifica chave NFS-e Nacional (50d) / NF-e (44d) + valida DV
    ├── cnpj_lookup     — enriquece cadastro via API pública (fallback chain)
    ├── SQLite          — cache de CCM por municipio::cnpj
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
    ├── resultado.xlsx   (19 colunas de resultado)
    ├── relatorio.html
    ├── logs/execution_<ts>.jsonl
    └── evidencias/
```

---

## Testes

```bash
python -m pytest tests/ -v
```

28 testes cobrindo: normalização CNPJ, **decode de chave NFS-e Nacional e NF-e com validação de DV (módulo 11)**, **cadeia de fallback de enriquecimento de CNPJ (HTTP mockado com respx)**, validação de modelos Pydantic, leitura do xlsx (25 linhas, 5 municípios, unicidade de cache key).

---

## Decisões técnicas

Ver [`docs/decisoes-tecnicas.md`](docs/decisoes-tecnicas.md) para detalhamento de:
- Verificação de URLs por HTTP antes de implementar
- Decisão por município (BH Sydle SPA, RJ CAPTCHA, Barueri Cloudflare, etc.)
- Rationale do cache SQLite e Strategy Pattern
- Tratamento de timeout e limitações conhecidas
