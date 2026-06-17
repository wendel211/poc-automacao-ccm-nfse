# Decisões Técnicas — POC CCM + NFS-e

## 1. Linguagem e stack

**Python como orquestrador principal.**

Motivo: melhor ecossistema para manipulação de Excel (pandas/openpyxl), validação de dados (Pydantic) e integração com Playwright via binding nativo. Evita necessidade de processo Node.js separado na POC.

Alternativa considerada e descartada: Node.js + Playwright puro (excelente para automação web, mas mais trabalhoso para manipulação de Excel e validação de dados tabulares).

## 2. Pydantic para validação de entrada

Cada linha da planilha passa por `InputRow` antes de qualquer I/O. Isso garante que CNPJs inválidos, municípios desconhecidos ou linhas sem código de verificação sejam rejeitados com mensagem clara antes de tentar acessar qualquer portal.

## 3. Detecção de chave NFS-e Nacional vs. código municipal

A planilha mistura dois formatos de `COD.VERIFICACAO`:
- **Chave longa (40+ dígitos numéricos)**: padrão NFS-e Nacional (ABRASF/SEFIN). Pode aparecer com espaços de agrupamento.
- **Código curto alfanumérico**: proprietário de cada portal municipal.

A função `is_nfse_nacional_key` em `utils/cnpj.py` faz esse roteamento. Isso evita que o conector errado tente processar uma chave que não entende.

## 4. Cache SQLite por município + CNPJ

Fornecedores aparecem duplicados na planilha (ex: FARIA E SILVA aparece em 2 linhas BH com mesmo CNPJ). Sem cache, faríamos 2 consultas idênticas ao portal. O cache SQLite garante que a segunda linha reutilize o resultado da primeira consulta.

## 5. Padrão de conectores (Strategy pattern)

Cada município implementa `MunicipalConnector` com a mesma interface:
- `lookup_ccm`
- `download_company_registration`
- `download_invoice`

O pipeline principal não sabe qual portal está acessando. Isso permite adicionar novos municípios sem tocar no orquestrador.

## 6. Playwright para portais sem API

Portais como BHISS Digital (BH) e Nota Carioca (RJ) não têm API pública estável. O Playwright em modo headless captura screenshots como evidência quando não consegue download direto do PDF.

**Estratégia de evidência progressiva:**
1. Tentar download direto do PDF/XML via HTTP
2. Se falhar, capturar screenshot da página de resultado como evidência
3. Registrar o erro técnico exato (timeout, HTTP status, ausência de PDF)

## 7. Retry com backoff exponencial (tenacity)

Portais municipais são instáveis. `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...))` em todos os conectores garante resiliência sem sobrecarregar os servidores.

## 8. Organização de evidências no filesystem

```
output/evidencias/<MUNICIPIO>/<CNPJ>/          # cadastro da empresa
output/evidencias/<MUNICIPIO>/<CNPJ>/notas/    # documentos de nota
```

Conforme especificado nas instruções. O slug do município usa ASCII sem acentos para compatibilidade cross-platform.

## 9. Coloração da planilha de saída

Linhas coloridas por status na planilha de resultado:
- Verde: SUCESSO
- Amarelo: PARCIAL (alguns downloads ok, outros não)
- Vermelho: ERRO
- Cinza: INDISPONIVEL

## 10. Desafios encontrados

**CCM não público**: nenhum dos 5 municípios da amostra expõe CCM sem autenticação no portal público. A POC registra isso como `INDISPONIVEL` e indica a necessidade de credenciais ou acesso via login.

**Chave da planilha truncada**: o campo `COD.VERIFICACAO` aparece truncado no Excel (reticências). O valor completo está disponível ao abrir o arquivo — o leitor `openpyxl` lê o valor completo sem truncamento.

**Portais JSF**: BHISS Digital e portal Porto Alegre usam JavaServer Faces. Os seletores CSS são gerados dinamicamente com IDs longos. A estratégia adotada foi usar seletores parciais (`id*=`, `name*=`) para robustez a mudanças de versão.
