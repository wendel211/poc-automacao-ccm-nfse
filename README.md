# poc-automacao-ccm-nfse

POC de automação fiscal: consulta de **CCM (Inscrição Municipal)** e download de documentos NFS-e para 5 municípios brasileiros, a partir de planilha de entrada.

## O que faz

Para cada linha da planilha de entrada:

1. Identifica município, CNPJ e código de verificação da nota
2. Consulta CCM/Inscrição Municipal da empresa no portal do município
3. Baixa o cadastro municipal da empresa (PDF, XML ou screenshot)
4. Baixa o documento da nota fiscal (PDF, XML ou screenshot)
5. Atualiza a planilha com status, CCM encontrado e caminhos dos arquivos

## Municípios suportados

| Município | Estratégia | Tipo de chave |
|---|---|---|
| Belo Horizonte | BHISS Digital (Playwright) + NFS-e Nacional | Chave longa (44+ dígitos) ou código curto |
| Rio de Janeiro | NFS-e Nacional (2026) + Nota Carioca (Playwright) | Chave longa ou código curto |
| Barueri | Portal Barueri NFS-e (HTTP + Playwright) | Código com pontos/hífen ou código curto |
| Porto Alegre | NFS-e Nacional + portal municipal (Playwright) | Chave longa ou código curto |
| Nova Lima | NFS-e Nacional (adesão jan/2026) + portal fallback | Chave longa ou código curto |

## Estrutura do projeto

```
.
├── src/
│   ├── main.py               # CLI (typer)
│   ├── pipeline.py           # Orquestrador principal
│   ├── models.py             # Modelos Pydantic (InputRow, RowResult, ...)
│   ├── excel_handler.py      # Leitura e escrita do .xlsx
│   ├── database.py           # Cache SQLite (CCM por município+CNPJ)
│   ├── connectors/           # Um conector por município
│   │   ├── base.py           # Interface abstrata MunicipalConnector
│   │   ├── barueri.py
│   │   ├── belo_horizonte.py
│   │   ├── rio_de_janeiro.py
│   │   ├── porto_alegre.py
│   │   ├── nova_lima.py
│   │   └── nfse_nacional.py  # Conector NFS-e Nacional (chaves longas)
│   ├── browser/
│   │   └── playwright_runner.py  # Automação de portais via Playwright
│   └── utils/
│       ├── cnpj.py           # Normalização e validação de CNPJ
│       └── filesystem.py     # Organização de pastas de evidência
├── tests/                    # Testes unitários (pytest)
├── input/                    # Planilha(s) de entrada
├── output/                   # Planilha de resultado + evidências (gerado)
├── docs/                     # Análise técnica e decisões
└── pyproject.toml
```

## Como rodar

### Pré-requisitos

- Python 3.11+
- pip

### Instalação

```bash
pip install -e ".[dev]"
playwright install chromium
```

### Executar

```bash
python -m src.main input/janabril2026_amostra_5x5.xlsx
```

Saída em `output/resultado_<timestamp>.xlsx` e evidências em `output/evidencias/`.

### Testes

```bash
python -m pytest tests/ -v
```

## Saída da planilha

Colunas adicionadas ao final:

| Coluna | Descrição |
|---|---|
| `STATUS_EXECUCAO` | SUCESSO / PARCIAL / ERRO / INDISPONIVEL |
| `MENSAGEM_TECNICA` | Detalhe do erro (timeout, captcha, HTTP status) |
| `CCM_ENCONTRADO` | Inscrição Municipal encontrada |
| `ARQUIVO_CADASTRO` | Caminho do cadastro municipal baixado |
| `ARQUIVO_NOTA_PDF` | Caminho do PDF da nota |
| `ARQUIVO_NOTA_XML` | Caminho do XML da nota |
| `MUNICIPIO_ESTRATEGIA` | Estratégia usada por município |
| `DATA_EXECUCAO` | Timestamp da execução |

## Estrutura de evidências

```
output/evidencias/
└── BELO_HORIZONTE/
    └── 28203865000174/
        ├── cadastro_28203865000174.png
        └── notas/
            └── 3106200222820386.pdf
```

## Limitações conhecidas

- Portais municipais podem exigir CAPTCHA — não há bypass automático implementado
- CCM não é exposto publicamente pela maioria dos municípios sem autenticação
- Mudanças de layout em portais JSF/ASP.NET podem quebrar os seletores Playwright
- NFS-e Nacional requer que o portal esteja disponível e sem bloqueio por IP/volume
