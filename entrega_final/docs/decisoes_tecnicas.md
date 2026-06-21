# Decisões Técnicas — POC CCM + Download de Documentos

Este documento descreve a arquitetura, as escolhas de tecnologia, as estratégias por município e as
decisões de engenharia adotadas na POC. O objetivo é deixar claro não só o que foi feito, mas também
por que cada caminho foi escolhido — e quais barreiras reais dos portais públicos limitam o resultado.

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

### Como o status é classificado (no código)

A classificação fica em `src/pipeline.py`:

- `cadastro_municipal_ok` = o conector retornou sucesso **e** existe um arquivo de cadastro com
  extensão aceita. As extensões de cadastro (`_CADASTRO_EXTS`) incluem `.pdf`, `.xml`, `.png`, `.jpg`
  — é o que permite o **print oficial** valer como cadastro.
- `nota_download_ok` = o conector retornou sucesso **e** existe arquivo de nota com extensão
  `.pdf`/`.xml` (`_NOTA_EXTS`). Print **não** conta como nota.
- `SUCESSO` exige `CCM` + `cadastro_municipal_ok` + `nota_download_ok`; `PARCIAL` se houver ao menos
  um; `ERRO` se não houver nenhum. Regra coberta por `tests/test_success_criteria.py`.

## Escolhas de tecnologia

- **Python ≥ 3.11** — velocidade de desenvolvimento e ecossistema maduro (Playwright, HTTP, Excel).
- **Typer + Rich + Loguru** — CLI tipada (`src/main.py`), tabela de progresso no terminal e logs
  legíveis + JSONL para auditoria.
- **httpx + tenacity** — fluxos HTTP diretos e retentativas; preferidos ao navegador quando o portal
  não exige browser (caminho mais curto e estável).
- **Playwright (Chromium)** — usado só onde há JavaScript/sessão/captcha/download/renderização: FIC
  BH, BHISS, Nota Carioca, SIAT/ISSQN POA, Certec RJ e o print da Consulta de Prestadores (Nova Lima).
- **Pydantic** — normaliza CNPJ, município, status e campos de resultado, reduzindo erro de formato.
- **pandas + openpyxl** — leitura/escrita da planilha final com as colunas técnicas.
- **SQLite** (`src/database.py`) — cache local de CCM e histórico de execuções.
- **ddddocr** — OCR local para captchas de **imagem** simples (fallback sem custo).
- **pytest + GitHub Actions** — testes das regras críticas, rodando em cada push/PR.

## Arquitetura

- Entrada: planilha `.xlsx` com CNPJ, município, referência e código/chave da nota.
- CLI: `src/main.py` → orquestração em `src/pipeline.py`.
- Modelos: `src/models.py`. Leitura/escrita da planilha: `src/excel_handler.py`. Relatório HTML:
  `src/report.py`. Cache: `src/database.py`.
- Conectores municipais: `src/connectors/` (um por município, interface comum em `base.py`).
- Serviços de portais/captcha: `src/services/`. Automação Playwright: `src/browser/playwright_runner.py`.
- Utilitários: `src/utils/` (chaves fiscais, CNPJ, filesystem).

Fluxo por linha:

1. ler e normalizar os dados (CNPJ, município);
2. decodificar e validar a chave fiscal;
3. selecionar o conector do município;
4. consultar CCM/Inscrição Municipal (com cache);
5. baixar o cadastro municipal;
6. baixar a nota fiscal;
7. classificar `SUCESSO`, `PARCIAL` ou `ERRO`;
8. gravar planilha, relatório, evidências e log JSONL.

## Decodificação das chaves fiscais

`src/utils/fiscal_keys.py` classifica e valida cada chave pelo tamanho/estrutura, com **dígito
verificador (módulo 11)**:

- **50 dígitos → NFS-e Nacional.** Extrai o município (código IBGE), o CNPJ emitente, o número e a
  competência. É o caminho com maior taxa de download real.
- **44 dígitos → NF-e (modelo 55) ou NFC-e (modelo 65).** Layout:
  `cUF(2) + AAMM(4) + CNPJ(14) + modelo(2) + série(3) + nNF(9) + tpEmis(1) + cNF(8) + DV(1)`.
  O modelo nas posições 21–22 distingue NF-e de NFC-e. Não é tratada como NFS-e municipal porque o
  documento completo depende de SEFAZ, certificado digital ou gov.br. Um modelo fora de 55/65 indica
  chave inválida na planilha (caso `2866704`, modelo `67`).
- **Códigos curtos** → verificação municipal específica (BHISS, Nota Carioca etc.).

Essa etapa evita consultar NF-e/NFC-e em portal de NFS-e, sinaliza CNPJ emitente divergente do
fornecedor da linha e ajuda a explicar os casos parciais.

## NFS-e Nacional (caminho curto em HTTP puro)

A consulta pública da NFS-e Nacional (`nfse.gov.br/consultapublica`) foi analisada manualmente: o
formulário é ASP.NET server-rendered **sem token anti-forgery**, e o único obstáculo é o hCaptcha.
Logo, todo o fluxo cabe em HTTP puro (sem navegador), em `src/services/nfse_nacional_download.py`:

1. `GET` da página (estabelece o cookie de sessão);
2. resolução do hCaptcha via 2Captcha;
3. `POST` do formulário com `ChaveAcesso` + `h-captcha-response`;
4. a resposta traz o link oficial `/ConsultaPublica/Download/DANFSe?chave=<token-de-sessão>`
   (o "chave" aqui é um token cifrado pelo servidor, não a chave de 50 dígitos);
5. `GET` desse link, na mesma sessão, baixa o **PDF real da DANFSe**.

Esse caminho é mais estável do que dirigir a UI do portal. Quando o portal responde uma mensagem
oficial (`Nota Fiscal de Serviço inexistente`), a automação registra o motivo e **não** marca sucesso
(caso `2653026`).

## Captcha e 2Captcha

`src/services/captcha_solver.py` usa a variável de ambiente `TWOCAPTCHA_API_KEY`. A chave real não
fica no repositório.

Tipos tratados:

- **hCaptcha** (NFS-e Nacional) — essa hCaptcha tem taxa de sucesso baixa por tentativa no 2Captcha
  (devolve `ERROR_CAPTCHA_UNSOLVABLE` com frequência). Por isso o solver **submete um lote de jobs em
  paralelo** e usa o **primeiro token resolvido**, com parsing tolerante (o `res.php` às vezes devolve
  texto/HTML em vez de JSON) e um teto total de tempo por captcha.
- **reCAPTCHA v2** (SIAT Porto Alegre) — método `userrecaptcha`; o token é injetado na página via
  Playwright para liberar a emissão do comprovante.
- **Captcha de imagem** (FIC BH, BHISS, Nota Carioca) — `ddddocr` local com fallback para a 2Captcha.

**Falha rápida (não trava o pipeline):**

- `_valid_api_key()` rejeita chave ausente, curta ou placeholder (ex.: contém "CHAVE"/"YOUR",
  `sua_chave_aqui`) — devolve `None` em ~0 s.
- Erros permanentes do 2Captcha (`ERROR_WRONG_USER_KEY`, `ERROR_ZERO_BALANCE`,
  `ERROR_KEY_DOES_NOT_EXIST`, IP banido) **abortam imediatamente** o solver, em vez de repetir até o
  teto de tempo. O resultado vira erro técnico na linha, e o pipeline segue.

## Cache e idempotência

`src/database.py` (SQLite `poc.db`) guarda o CCM por município/CNPJ e registra as execuções. Além
disso, cada serviço **reaproveita o PDF/print já baixado** quando o arquivo existe e é válido
(`> 1000 bytes`). Resultado: reexecuções **não refazem** trabalho concluído nem consomem captcha à
toa — útil para retomar uma execução interrompida (basta rodar de novo que só o que faltou é tentado).

## Estratégias por município

### Belo Horizonte

- **Cadastro:** FIC pública da PBH (`mobiliarioonline.pbh.gov.br`) via Playwright e captcha de imagem;
  o parser prefere a inscrição **ativa** quando há mais de uma para o CNPJ.
- **Nota:** se a chave é NFS-e Nacional (50 díg), roteia para o fluxo nacional; se é código curto,
  usa o BHISS (`bhissdigital.pbh.gov.br`, JSF) com CNPJ + número (formato `AAAA/N`) + código de
  verificação + captcha de imagem, tentando os anos 2026→2023.
- Chave NF-e de 44 dígitos **não** é tratada como NFS-e.

### Rio de Janeiro

- **Cadastro:** Certec RJ (`certec.apps.rio.gov.br`) — "Comprovante de Inscrição e de Situação
  Cadastral" com a Inscrição Municipal.
- **Nota:** NFS-e Nacional para chaves nacionais; Nota Carioca (`notacarioca.rio.gov.br`, WebForms +
  captcha de imagem) para códigos curtos. Screenshot da Nota Carioca **não** é aceito como nota.

### Porto Alegre

- **Cadastro:** SIAT/ISSQN (`siat.procempa.com.br`) com Playwright, **reCAPTCHA** e chamada interna
  GWT, baixando o "Comprovante de inscrição no cadastro de ISSQN" em PDF oficial.
- **Nota:** NFS-e Nacional quando a chave é nacional; portal municipal
  (`nfe-web.portoalegre.rs.gov.br`) para códigos curtos.

### Nova Lima

- **Inscrição:** confirmada pela Consulta de Prestadores pública do e-NFS
  (`e-nfs.com.br/e-nfs_novalima`, servlet `servicosportaljson` / ação `CNSPRESTADORES`).
- **Cadastro:** print oficial da página de Consulta de Prestadores (Playwright), mostrando razão
  social, CNPJ e Inscrição Municipal — validado antes de salvar. Aceito pelo enunciado como "Print da
  Página de Cadastro".
- Quando a chave NFS-e Nacional aponta para Belo Horizonte, a FIC BH é usada como fonte municipal
  correta (casos `2461162`/`2661928`).

### Barueri

- O ISSNet (`issnetonline.com.br`) foi acessado com Playwright/contexto stealth, mas permanece
  bloqueado por **Cloudflare 403**.
- O portal oficial alternativo (`servicos.barueri.sp.gov.br/emissaocertidao/certidaocadastral.aspx`)
  é público, mas **exige a Inscrição Municipal como entrada** (não basta o CNPJ), que não consta na
  planilha. Por isso o cadastro de Barueri não é obtenível de forma automática a partir do CNPJ.

## Saída e auditabilidade

- **Planilha** (`src/excel_handler.py`): além das colunas originais, grava `STATUS_EXECUCAO`,
  `MENSAGEM_TECNICA`, `CCM`/`CCM_ENCONTRADO`, dados da nota (município, número, competência,
  conferência de CNPJ emitente, validade do DV) e os caminhos dos arquivos baixados. A coluna `CCM`
  original é preenchida quando a inscrição é encontrada (requisito do enunciado).
- **Relatório HTML** (`src/report.py`) com o resumo e a tabela por linha.
- **Log JSONL** por execução, para auditoria técnica.

## Integridade e limpeza técnica

- Foi removido o PDF de Joaçaba/SC usado em versão anterior para SALT/Nova Lima, porque era de outro
  município e não comprovava cadastro de Nova Lima (evitar falso positivo).
- Foi removido o código legado que gerava PDF local a partir de cadastro federal e JSON de chave
  fiscal, pois isso não satisfaz o critério real de sucesso.
- O pipeline mantém somente documentos oficiais baixados, ou o print oficial de página de cadastro
  quando o enunciado permite. A planilha final foi auditada (0 caminhos quebrados, sem `nan`).

## Limitações conhecidas (barreiras reais dos portais)

- **NF-e/NFC-e (44 díg):** o documento fiscal completo não é público — exige certificado digital
  ICP-Brasil / manifestação do destinatário. Afeta `2709821`, `2731793`, `2866704`.
- **Portais bloqueados/instáveis:** ISSNet/Barueri (Cloudflare 403); Nota Carioca exige o CNPJ na
  base de prestadores; alguns portais municipais ficaram fora do ar em janelas da execução.
- **hCaptcha instável** no 2Captcha — mitigado por lote paralelo, mas pode exigir reexecução.
- **Dados da planilha:** há linhas com CNPJ emitente da chave divergente do fornecedor
  (`2895618`, `2856841`) e chave com modelo inválido (`2866704`).

## Validação local

```text
48 passed
```
