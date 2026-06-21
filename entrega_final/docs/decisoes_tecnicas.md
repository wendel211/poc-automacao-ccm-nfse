# Decisões Técnicas — POC CCM + Download de Documentos

Este documento descreve a arquitetura, as escolhas de tecnologia, as estratégias por município e as
decisões de engenharia adotadas na POC. O objetivo é deixar claro não só o que foi feito, mas também
por que cada caminho foi escolhido.

## Critério de sucesso

Uma linha só é marcada como `SUCESSO` quando possui os três itens:

1. Inscrição Municipal / CCM encontrada.
2. Cadastro municipal oficial da empresa em PDF/XML ou print da página de cadastro do portal oficial
   do município.
3. Nota fiscal oficial baixada em PDF ou XML.

Não contam como sucesso:

- cadastro federal/público de apoio, como ReceitaWS, CNPJa ou BrasilAPI;
- JSON de chave fiscal decodificada;
- PDF gerado localmente pela própria automação;
- print que não seja página oficial de cadastro municipal;
- documento de outro município;
- caso com apenas cadastro ou apenas nota.

O print de cadastro só é aceito quando vem da página oficial do município e mostra a empresa correta
com CNPJ e Inscrição Municipal. A nota fiscal continua exigindo PDF ou XML; print de nota não vira
sucesso.

## Escolhas de tecnologia

### Python

Python foi usado pela velocidade de desenvolvimento da POC e pelo ecossistema maduro para:

- automação web com Playwright;
- chamadas HTTP com controle fino;
- manipulação de planilhas Excel;
- validação de dados;
- testes rápidos.

### Typer

`typer` foi escolhido para a CLI por ser simples, tipado e legível. O comando principal fica em
`src/main.py` e recebe a planilha e o diretório de saída. O passo a passo de execução fica apenas
no `README.md`.

### Playwright

Playwright/Chromium foi usado nos portais que exigem browser real, JavaScript, sessão, captcha,
download ou renderização de página:

- FIC BH;
- BHISS/NFS-e municipal;
- Nota Carioca;
- SIAT/ISSQN Porto Alegre;
- Certec RJ;
- e-NFS Nova Lima, para o print oficial da Consulta de Prestadores.

Onde foi possível usar HTTP direto, o Playwright foi evitado para reduzir fragilidade e tempo de
execução.

### HTTPX

`httpx` foi usado nos fluxos HTTP diretos, especialmente NFS-e Nacional, consultas auxiliares e
endpoints JSON. Isso permitiu caminhos mais curtos, com menos barreiras de UI, quando o portal
não exigia navegador.

### Pydantic

`pydantic` foi usado nos modelos de entrada/saída para normalizar CNPJ, município, status e campos
de resultado, reduzindo erro de formato ao gravar a planilha.

### Pandas e OpenPyXL

`pandas` e `openpyxl` foram usados para ler e escrever a planilha final, mantendo colunas técnicas,
status, mensagens e caminhos dos arquivos baixados.

### SQLite

SQLite (`src/database.py`) foi usado como cache local:

- evita repetir consultas de CCM já resolvidas;
- registra execuções;
- reduz consumo de captcha e tempo em reexecuções.

### Rich e Loguru

`rich` exibe a tabela de progresso no terminal. `loguru` gera logs legíveis e em JSONL para auditoria
técnica.

### Pytest

`pytest` cobre regras críticas:

- critério de sucesso;
- aceitação de cadastro em PDF/XML/print;
- rejeição de print como nota;
- parsing de CNPJ/chaves fiscais;
- conectores/serviços principais;
- comportamento da 2Captcha quando a chave é placeholder.

## Arquitetura

- Entrada: planilha `.xlsx` com CNPJ, município, referência e código/chave da nota.
- CLI: `src/main.py`.
- Orquestração: `src/pipeline.py`.
- Modelos: `src/models.py`.
- Leitura/escrita da planilha: `src/excel_handler.py`.
- Relatório HTML: `src/report.py`.
- Cache SQLite: `src/database.py`.
- Conectores municipais: `src/connectors/`.
- Serviços de portais/captcha: `src/services/`.
- Automação Playwright: `src/browser/playwright_runner.py`.
- Utilitários: `src/utils/`.

Fluxo por linha:

1. ler os dados da planilha;
2. normalizar CNPJ e município;
3. decodificar/validar a chave fiscal;
4. selecionar o conector do município;
5. consultar CCM/Inscrição Municipal;
6. baixar o cadastro municipal;
7. baixar a nota fiscal;
8. classificar `SUCESSO`, `PARCIAL` ou `ERRO`;
9. gravar planilha, relatório, evidências e log JSONL.

## Decodificação das chaves fiscais

`src/utils/fiscal_keys.py` classifica e valida as chaves:

- 50 dígitos: NFS-e Nacional, com município IBGE, CNPJ emitente, número e competência.
- 44 dígitos: NF-e/NFC-e. Não é tratada como NFS-e municipal porque o documento completo depende
  de SEFAZ, certificado digital ou gov.br.
- Códigos curtos: consulta municipal específica.

Essa etapa evita tentar consultar NF-e/NFC-e em portal de NFS-e e ajuda a explicar os casos parciais.

## NFS-e Nacional

A consulta pública da NFS-e Nacional foi automatizada por HTTP puro:

1. `GET` da página pública;
2. resolução do hCaptcha via 2Captcha;
3. `POST` do formulário;
4. captura do link oficial `/Download/DANFSe`;
5. download do PDF real da DANFSe.

Esse caminho foi preferido por ser mais estável do que controlar a UI do portal. Quando o portal
retorna uma mensagem oficial, como `Nota Fiscal de Serviço inexistente`, a automação registra a
mensagem e não marca sucesso.

## Captcha e 2Captcha

`src/services/captcha_solver.py` usa a variável de ambiente `TWOCAPTCHA_API_KEY`. A chave real não
fica no repositório.

Tipos tratados:

- hCaptcha: NFS-e Nacional;
- reCAPTCHA v2: SIAT Porto Alegre;
- captcha de imagem: FIC BH, BHISS e Nota Carioca;
- fallback local com `ddddocr` para captchas de imagem simples.

Para o hCaptcha, a POC submete jobs em lote e usa o primeiro token resolvido, porque esse tipo de
captcha pode falhar ou demorar. Se a chave estiver ausente, curta ou como placeholder, o resolvedor
falha rápido e registra erro técnico, em vez de travar o pipeline.

## Estratégias por município

### Belo Horizonte

- Cadastro municipal: FIC pública da PBH via Playwright e captcha de imagem.
- O parser prefere a inscrição ativa quando há mais de uma inscrição para o CNPJ.
- Nota municipal curta: BHISS/NFS-e com CNPJ, número, código de verificação e captcha.
- Para referências curtas, tenta os anos 2026, 2025, 2024 e 2023.
- Chave NF-e de 44 dígitos não é tratada como NFS-e.

### Rio de Janeiro

- Cadastro municipal: Certec RJ quando o portal libera a consulta.
- Nota: NFS-e Nacional para chaves nacionais; Nota Carioca para códigos curtos, com Playwright e
  captcha de imagem.
- Screenshot da Nota Carioca não é aceito como nota fiscal baixada.

### Porto Alegre

- Cadastro municipal: SIAT/ISSQN com Playwright, reCAPTCHA e chamada interna GWT.
- Nota: NFS-e Nacional quando a chave é nacional; portal municipal para códigos curtos.
- Os comprovantes de ISSQN são baixados como PDF oficial.

### Nova Lima

- O e-NFS Nova Lima confirma a inscrição municipal quando há dados públicos.
- Para a SALT Tecnologia, CNPJ `56.422.955/0001-91`, a Consulta de Prestadores retorna a IM `29657884`.
- O cadastro municipal usado é o print oficial da página de Consulta de Prestadores, mostrando razão
  social, CNPJ e inscrição municipal. Isso atende ao enunciado.
- Quando a chave aponta para Belo Horizonte, a FIC BH é usada como fonte municipal correta.

### Barueri

- O ISSNet foi acessado com Playwright/contexto stealth.
- O portal permaneceu bloqueado por Cloudflare 403.
- A nota NFS-e Nacional pode ser baixada em caso parcial, mas sem cadastro/CCM oficial de Barueri não vira sucesso.

## Integridade e limpeza técnica

- Foi removido o PDF de Joaçaba/SC usado em versão anterior para SALT/Nova Lima, porque não comprovava
  cadastro de Nova Lima.
- Foi removido o código legado que gerava PDF local a partir de cadastro federal e JSON de chave
  fiscal, pois isso não satisfaz o critério real de sucesso.
- O pipeline mantém somente documentos oficiais baixados, ou o print oficial de página de cadastro
  quando o enunciado permite.
- A planilha final foi auditada para não conter caminhos quebrados.

## Validação local

```text
48 passed
```
