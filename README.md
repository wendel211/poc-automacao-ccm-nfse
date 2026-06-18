# POC de Automação - CCM + Download de Documentos NFS-e

Automação fiscal que lê uma planilha de entrada, consulta o **CCM (Inscrição Municipal)** de cada empresa e faz o download dos documentos fiscais (cadastro municipal + nota fiscal) nos portais de 5 municípios brasileiros.

![Demo do pipeline](gifpoc.gif)

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

### Busca oficial na NFS-e Federal (API SEFIN Nacional + mTLS)

O canal **sancionado** para baixar a NFS-e Nacional por chave é a API SEFIN/ADN Nacional, que exige **certificado digital ICP-Brasil** (e-CNPJ A1) via mTLS — o endpoint responde `496 SSL certificate required` sem ele. Esse cliente está implementado em [`src/services/sefin_nacional.py`](src/services/sefin_nacional.py): com um certificado configurado, o pipeline baixa o XML real da nota; sem ele, registra a tentativa e cai para a evidência da consulta pública.

```bash
# Converter e-CNPJ A1 (.pfx) para PEM e apontar para o pipeline:
openssl pkcs12 -in ecnpj.pfx -clcerts -nokeys -out cert.pem
openssl pkcs12 -in ecnpj.pfx -nocerts -nodes  -out key.pem
export NFSE_CERT_PEM=cert.pem NFSE_KEY_PEM=key.pem
```

> Os portais públicos (consulta pública com hCaptcha, Emissor Nacional com login gov.br) não permitem fetch programático — verificado empiricamente. A API com certificado é o único caminho oficial, e está pronto para produção.

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

### Demonstração da busca na NFS-e Federal (SEFIN + mTLS)

```bash
python scripts/demo_sefin.py
```

Mostra ao vivo: (1) que os endpoints oficiais respondem `496/403` sem certificado, (2) o cliente degradando com mensagem clara, e (3) o caminho de download real quando um e-CNPJ A1 está configurado.

---

## Saídas geradas

```
output/
├── resultado_<timestamp>.xlsx       # planilha com 20 colunas de resultado
├── relatorio_<timestamp>.html       # relatório HTML com screenshots embutidos
├── logs/execution_<timestamp>.jsonl # log estruturado por linha
└── evidencias/
    └── <MUNICIPIO>/
        └── <CNPJ>/
            ├── comprovante_cadastro_<CNPJ>.pdf  # cadastro gerado a partir dos dados da Receita
            ├── cadastro_<CNPJ>.png              # screenshot do portal (evidência)
            └── notas/
                ├── dados_nota_<n>.json          # dados decodificados e validados da chave
                └── nfse_nacional_<chave>.png    # screenshot do portal (evidência)
```

Além das colunas na planilha, cada empresa recebe um **comprovante de cadastro em PDF** (gerado a partir dos dados da Receita) e cada nota com chave decodificável recebe um **JSON estruturado** com os campos extraídos e validados — artefatos baixáveis reais, já que os portais não liberam o download oficial.

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
| `ARQUIVO_CADASTRO` | Caminho do comprovante de cadastro em PDF gerado |
| `ARQUIVO_DADOS_NOTA` | Caminho do JSON com os dados decodificados da nota |
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
    ├── sefin_nacional  — baixa XML da NFS-e via API SEFIN (mTLS ICP-Brasil)
    ├── document_builder — gera comprovante PDF + JSON da nota (artefatos baixáveis)
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

33 testes cobrindo: normalização CNPJ, **decode de chave NFS-e Nacional e NF-e com validação de DV (módulo 11)**, **cadeia de fallback de enriquecimento de CNPJ (HTTP mockado com respx)**, **geração de artefatos (PDF de cadastro e JSON da nota)**, **cliente SEFIN Nacional mTLS (com e sem certificado)**, validação de modelos Pydantic, leitura do xlsx (25 linhas, 5 municípios, unicidade de cache key).

---

## Decisões técnicas

Ver [`docs/decisoes-tecnicas.md`](docs/decisoes-tecnicas.md) para detalhamento de:
- Verificação de URLs por HTTP antes de implementar
- Decisão por município (BH Sydle SPA, RJ CAPTCHA, Barueri Cloudflare, etc.)
- Rationale do cache SQLite e Strategy Pattern
- Tratamento de timeout e limitações conhecidas
