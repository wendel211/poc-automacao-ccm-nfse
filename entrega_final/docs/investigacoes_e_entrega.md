# Investigações e Entrega — POC CCM + Download de Documentos

Este documento consolida o resultado por linha da amostra, os casos de sucesso, os portais usados
por município e os motivos técnicos dos casos `PARCIAL` e `ERRO`.

## Artefatos finais

- Planilha final: `entrega_final/resultados/resultado_final_entrega_20260620.xlsx`
- Relatório HTML: `entrega_final/resultados/relatorio_final_entrega_20260620.html`
- Evidências reais: `entrega_final/evidencias/`
- Decisões técnicas: `entrega_final/docs/decisoes_tecnicas.md`
- Este documento: `entrega_final/docs/investigacoes_e_entrega.md`

As evidências reais já estão em `entrega_final/evidencias/`. A reexecução do zero é opcional e
depende da disponibilidade dos portais públicos e de uma chave válida da 2Captcha via
`TWOCAPTCHA_API_KEY`.

## Resultado final

- Total: 25 linhas.
- **SUCESSO: 11.**
- **PARCIAL: 5.**
- **ERRO: 9.**
- Caminhos auditados na planilha final: 0 links quebrados, sem `nan`.
- Testes automatizados: 48 passed.

## Validação com chave real da 2Captcha

A pipeline foi executada de ponta a ponta com uma chave real da 2Captcha. Confirmou-se que, com a
chave, o **hCaptcha da NFS-e Nacional é resolvido** e as **DANFSe são baixadas de verdade** — por
exemplo, os casos `2652712`/`2665465` (DANFSe 24) e `2632698` (DANFSe 10) baixaram a nota real e
ficaram `SUCESSO`. Sem a chave, esses mesmos passos registram o erro técnico
"hCaptcha não resolvido" e não marcam sucesso (a pipeline falha rápido, não trava). Ou seja, o
resultado `11 SUCESSO` é reprodutível com chave válida e portais no ar.

## Portais por município

| Município | Cadastro municipal (portal) | Nota fiscal (portal) | Captcha |
|---|---|---|---|
| Belo Horizonte | FIC pública (`mobiliarioonline.pbh.gov.br`) | NFS-e Nacional ou BHISS (`bhissdigital.pbh.gov.br`) | imagem / hCaptcha |
| Rio de Janeiro | Certec (`certec.apps.rio.gov.br`) | NFS-e Nacional ou Nota Carioca (`notacarioca.rio.gov.br`) | imagem / hCaptcha |
| Porto Alegre | SIAT/ISSQN (`siat.procempa.com.br`) | NFS-e Nacional ou portal municipal (`nfe-web.portoalegre.rs.gov.br`) | reCAPTCHA / imagem / hCaptcha |
| Nova Lima | e-NFS — Consulta de Prestadores (`e-nfs.com.br/e-nfs_novalima`) ou FIC BH quando a chave aponta BH | NFS-e Nacional ou BHISS | sem captcha / hCaptcha |
| Barueri | ISSNet (`issnetonline.com.br`) — bloqueado por Cloudflare 403 | NFS-e Nacional (quando há chave) | Cloudflare / hCaptcha |

NFS-e Nacional: `nfse.gov.br/consultapublica` (download oficial em `/Download/DANFSe`).

## Casos de sucesso confirmados

Cada linha tem **cadastro municipal oficial** + **nota fiscal oficial**, ambos em
`entrega_final/evidencias/`.

| ID | Município | CNPJ | CCM/IM | Cadastro oficial | Nota oficial |
|---|---|---|---|---|---|
| 2652712 | Belo Horizonte | 28.203.865/0001-74 | 10380110013 | FIC BH (PDF) | DANFSe 24 (PDF) |
| 2665465 | Belo Horizonte | 28.203.865/0001-74 | 10380110013 | FIC BH (PDF) | DANFSe 24 (PDF) |
| 2632698 | Rio de Janeiro | 12.977.432/0001-36 | 4966457 | Certec RJ (PDF) | DANFSe 10 (PDF) |
| 2639235 | Porto Alegre | 15.486.022/0001-80 | 605.598.2.9 | SIAT ISSQN (PDF) | DANFSe 123 (PDF) |
| 1564830 | Porto Alegre | 90.347.840/0051-87 | 229.203.2.3 | SIAT ISSQN (PDF) | NFS-e municipal 2022/21372 (PDF) |
| 2643938 | Porto Alegre | 15.486.022/0001-80 | 605.598.2.9 | SIAT ISSQN (PDF) | DANFSe 194 (PDF) |
| 2654015 | Porto Alegre | 29.739.737/0006-17 | 005.489.2.8 | SIAT ISSQN (PDF) | DANFSe 6997 (PDF) |
| 2461162 | Nova Lima/BH | 10.999.280/0001-47 | 02433830022 | FIC BH (PDF) | NFS-e municipal 2025/1501 (PDF) |
| 2661928 | Nova Lima/BH | 10.999.280/0001-47 | 02433830022 | FIC BH (PDF) | DANFSe 135 (PDF) |
| 2660802 | Nova Lima | 56.422.955/0001-91 | 29657884 | Print oficial e-NFS (PNG) | DANFSe 1610 (PDF) |
| 2675393 | Nova Lima | 56.422.955/0001-91 | 29657884 | Print oficial e-NFS (PNG) | DANFSe 1610 (PDF) |

## Situação por linha

| ID | Município | CNPJ | Status | Situação |
|---|---|---|---|---|
| 2652712 | Belo Horizonte | 28.203.865/0001-74 | SUCESSO | FIC BH e DANFSe 24 baixadas. |
| 2586757 | Belo Horizonte | 09.346.601/0021-79 | ERRO | FIC BH não encontrou inscrição; NFS-e BH testada em 2026/1133, 2025/1133, 2024/1133 e 2023/1133; o portal não localizou registro. |
| 2709821 | Belo Horizonte | 07.221.102/0001-86 | PARCIAL | Cadastro FIC BH e CCM `01930260013` existem; a nota é NF-e modelo 55, dependente de SEFAZ/certificado. |
| 2879950 | Belo Horizonte | 92.966.571/0003-65 | ERRO | FIC BH não encontrou inscrição; NFS-e BH testada em 2026/173, 2025/173, 2024/173 e 2023/173; o portal não localizou registro. |
| 2665465 | Belo Horizonte | 28.203.865/0001-74 | SUCESSO | Mesmo fornecedor/documentos do 2652712. |
| 2632698 | Rio de Janeiro | 12.977.432/0001-36 | SUCESSO | Certec RJ trouxe a IM `4966457`; DANFSe 10 baixada. |
| 2716126 | Rio de Janeiro | 13.952.675/0001-82 | ERRO | Nota Carioca submetida com captcha resolvido; retorno oficial `Contribuinte não encontrado`; CNPJ ausente da lista DSPREST. |
| 2726315 | Rio de Janeiro | 06.028.498/0001-87 | ERRO | Nota Carioca submetida com captcha resolvido; retorno oficial `Contribuinte não encontrado`; CNPJ ausente da lista DSPREST. |
| 2731793 | Rio de Janeiro | 28.037.401/0001-35 | ERRO | O CNPJ aparece como prestador (Certec IM `10603692`), mas a nota da linha é NF-e modelo 55; DANFE/XML oficial exige SEFAZ/certificado. |
| 2653026 | Rio de Janeiro | 08.154.258/0001-54 | PARCIAL | CCM `3923614` encontrado; a NFS-e Nacional retornou `Nota Fiscal de Serviço inexistente` para a DANFSe 12. |
| 2625718 | Barueri | 03.528.670/0001-73 | ERRO | ISSNet bloqueado por Cloudflare 403. |
| 2637026 | Barueri | 65.704.413/0027-31 | ERRO | ISSNet bloqueado por Cloudflare 403. |
| 2895618 | Barueri | 00.489.803/0001-51 | PARCIAL | DANFSe 3163 baixada pela NFS-e Nacional; falta cadastro/CCM de Barueri e a chave aponta para CNPJ emitente divergente (Curitiba). |
| 2802593 | Barueri | 62.307.848/0001-15 | ERRO | ISSNet bloqueado por Cloudflare 403. |
| 2644033 | Barueri | 03.528.670/0001-73 | ERRO | Mesmo fornecedor do 2625718; ISSNet bloqueado por Cloudflare 403. |
| 2639235 | Porto Alegre | 15.486.022/0001-80 | SUCESSO | SIAT ISSQN e DANFSe 123 baixados. |
| 2866704 | Porto Alegre | 09.262.608/0016-45 | PARCIAL | SIAT ISSQN e CCM `292.423.2.0` baixados; a nota é NFC-e/modelo 67, dependente de SEFAZ/gov.br. |
| 1564830 | Porto Alegre | 90.347.840/0051-87 | SUCESSO | SIAT ISSQN e NFS-e municipal 2022/21372 baixados. |
| 2643938 | Porto Alegre | 15.486.022/0001-80 | SUCESSO | SIAT ISSQN e DANFSe 194 baixados. |
| 2654015 | Porto Alegre | 29.739.737/0006-17 | SUCESSO | SIAT ISSQN e DANFSe 6997 baixados. |
| 2660802 | Nova Lima | 56.422.955/0001-91 | SUCESSO | IM `29657884` confirmada no e-NFS; print oficial da Consulta de Prestadores + DANFSe 1610. |
| 2461162 | Nova Lima/BH | 10.999.280/0001-47 | SUCESSO | FIC BH com IM ativa `02433830022`; NFS-e municipal 2025/1501 baixada. |
| 2675393 | Nova Lima | 56.422.955/0001-91 | SUCESSO | Mesmo caso SALT do 2660802; print oficial da Consulta de Prestadores + DANFSe 1610. |
| 2856841 | Nova Lima | 05.777.093/0001-89 | PARCIAL | DANFSe 1742 baixada; o CNPJ emitente da chave (`03881239...`) diverge do fornecedor e não há cadastro/IM municipal confirmado. |
| 2661928 | Nova Lima/BH | 10.999.280/0001-47 | SUCESSO | FIC BH com IM ativa `02433830022`; DANFSe 135 baixada. |

## Investigações relevantes

### SALT / Nova Lima

O e-NFS Nova Lima confirma a SALT TECNOLOGIA LTDA, CNPJ `56.422.955/0001-91`, com inscrição
municipal `29657884`. A nota 1610 foi baixada pela NFS-e Nacional.

O cadastro municipal é o **print oficial da página de Consulta de Prestadores do e-NFS Nova Lima**
(`cadastro_municipal_nova_lima_enfs_56422955000191.png`), capturado ao vivo com Playwright e
validado: a página renderiza razão social, CNPJ e Inscrição Municipal antes do print ser salvo.
Como o enunciado aceita "Print da Página de Cadastro", os casos `2660802` e `2675393` são sucesso.

Importante: foi **removido** um PDF usado em versão anterior porque vinha de `joacaba.sc.gov.br`
(outro município, em Santa Catarina) e não comprovava cadastro de Nova Lima — seria um falso
positivo.

### Rio de Janeiro

Para `2716126` e `2726315`, a Nota Carioca foi acessada com Playwright real, captcha de imagem
resolvido e formulário submetido. O retorno oficial foi `Contribuinte não encontrado`, e a lista
pública de prestadores (DSPREST) também não contém os CNPJs.

Para `2731793`, o CNPJ aparece como prestador (Certec retorna a IM `10603692`), mas o documento da
linha é NF-e modelo 55; o download oficial de DANFE/XML completo depende de SEFAZ/certificado, então
o caso fica sem nota.

### NF-e / NFC-e (chaves de 44 dígitos)

Os casos `2709821`, `2731793` e `2866704` usam chave NF-e/NFC-e de 44 dígitos, não NFS-e municipal.
Foram investigados os caminhos públicos:

- **Portal Nacional da NF-e** (`nfe.fazenda.gov.br`): a consulta pública só devolve o *resumo*
  (situação) após reCAPTCHA; o **DANFE/XML completo exige certificado digital ICP-Brasil**
  (manifestação do destinatário). Sem certificado, não há documento.
- **meudanfe.com.br** (terceiro): os endpoints reais são `/v2/fd/get/xml/{chave}` e
  `/v2/fd/get/da/{chave}`, mas a busca é protegida por **Cloudflare Turnstile** e só serve XML do
  **acervo colaborativo** deles; o próprio código avisa que há **API paga**. Não é fonte oficial.
- O `2866704` ainda tem chave com **modelo `67`**, inválido (só existem 55 = NF-e e 65 = NFC-e),
  o que indica chave incorreta na planilha — nenhum portal a reconhece.

Por isso esses casos não foram promovidos a sucesso (têm cadastro municipal real, mas falta a nota).

### Barueri

O ISSNet (`issnetonline.com.br`) permanece **bloqueado por Cloudflare 403** mesmo com contexto
stealth. Foi investigado o portal oficial alternativo da Prefeitura
(`servicos.barueri.sp.gov.br/emissaocertidao/certidaocadastral.aspx`): ele é público e emite a
Certidão Cadastral, mas **exige a Inscrição Municipal como entrada** (não basta o CNPJ) — e a IM
não está disponível na planilha. Mesmo obtendo o cadastro, as notas de Barueri continuam atrás do
ISSNet (403) ou são chave de outro município/divergente. Por isso os casos seguem `ERRO`/`PARCIAL`.

O caso `2895618` tem nota NFS-e Nacional baixada (3163), mas a chave pertence a emitente de
**Curitiba** (`05.563.889/...`), divergente do fornecedor da linha — não pode ser sucesso da linha.

### Belo Horizonte com código curto

Os casos `2586757` e `2879950` foram testados no portal BH NFS-e (BHISS) com Playwright e captcha.
Além do número informado na planilha, foram testadas variações de ano (`2026`, `2025`, `2024` e
`2023`). O retorno oficial foi que o sistema não localizou registro, e a FIC também não encontrou
inscrição em BH para esses CNPJs.

## Conclusão

A entrega final mantém **somente evidências oficiais reais**. Conforme o enunciado, são aceitos:

- **cadastro municipal**: PDF, XML **ou print/screenshot da página oficial de cadastro** (ex.: o print
  da Consulta de Prestadores do e-NFS Nova Lima);
- **nota fiscal**: PDF **ou XML**.

Não entram cadastro federal de apoio, JSON de chave, PDF gerado localmente nem documento de outro
município. Os casos sem fonte oficial pública suficiente permanecem `PARCIAL` ou `ERRO`, sem mascarar.
O número honesto de sucessos é **11**.
