"""Orquestrador principal: lê planilha → processa por município → grava resultados."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from src.connectors.barueri import BarueriConnector
from src.connectors.base import MunicipalConnector
from src.connectors.belo_horizonte import BeloHorizonteConnector
from src.connectors.nova_lima import NovaLimaConnector
from src.connectors.porto_alegre import PortoAlegreConnector
from src.connectors.rio_de_janeiro import RioDeJaneiroConnector
from src.database import Database
from src.excel_handler import read_rows, write_results
from src.models import InputRow, Municipio, RowResult, StatusExecucao
from src.services.cnpj_lookup import CompanyData, fetch_company_data
from src.utils.cnpj import normalize as normalize_cnpj
from src.utils.fiscal_keys import TipoChave, decode as decode_chave
from src.utils.filesystem import ensure_dirs

_CONNECTORS: dict[Municipio, MunicipalConnector] = {
    Municipio.BELO_HORIZONTE: BeloHorizonteConnector(),
    Municipio.RIO_DE_JANEIRO: RioDeJaneiroConnector(),
    Municipio.BARUERI: BarueriConnector(),
    Municipio.PORTO_ALEGRE: PortoAlegreConnector(),
    Municipio.NOVA_LIMA: NovaLimaConnector(),
}

_STATUS_STYLE = {
    StatusExecucao.SUCESSO: "bold green",
    StatusExecucao.PARCIAL: "bold yellow",
    StatusExecucao.ERRO: "bold red",
    StatusExecucao.INDISPONIVEL: "dim",
}

_STATUS_ICON = {
    StatusExecucao.SUCESSO: "[OK]",
    StatusExecucao.PARCIAL: "[~]",
    StatusExecucao.ERRO: "[X]",
    StatusExecucao.INDISPONIVEL: "[-]",
}

_CADASTRO_EXTS = {".pdf", ".xml", ".png", ".jpg", ".jpeg"}
_NOTA_EXTS = {".pdf", ".xml"}

import io, sys as _sys
_stdout_utf8 = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
console = Console(file=_stdout_utf8, highlight=False)


def _has_file(path: str | None, allowed_exts: set[str]) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.suffix.lower() in allowed_exts and p.exists()


def _classify_status(
    *,
    ccm_value: str | None,
    cadastro_municipal_ok: bool,
    nota_download_ok: bool,
) -> StatusExecucao:
    if ccm_value and cadastro_municipal_ok and nota_download_ok:
        return StatusExecucao.SUCESSO
    if ccm_value or cadastro_municipal_ok or nota_download_ok:
        return StatusExecucao.PARCIAL
    return StatusExecucao.ERRO


def _build_table(rows: list[InputRow], results: dict[str, RowResult], current_id: str | None) -> Table:
    table = Table(
        title="[bold cyan]POC Automação CCM + NFS-e[/bold cyan]",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", width=9)
    table.add_column("Município", width=18)
    table.add_column("CNPJ", width=18)
    table.add_column("Status", width=14)
    table.add_column("Evidência", width=10)
    table.add_column("Mensagem", overflow="fold")

    for i, row in enumerate(rows, 1):
        result = results.get(row.id_documento)
        if result:
            status = result.status
            style = _STATUS_STYLE[status]
            icon = _STATUS_ICON[status]
            evidencia = "sim" if (
                result.arquivo_cadastro
                or result.arquivo_nota_pdf
                or result.arquivo_nota_xml
                or result.arquivo_evidencia_cadastro
                or result.arquivo_evidencia_nota
                or result.arquivo_evidencia
            ) else "nao"
            msg = (result.mensagem_tecnica or "")[:60]
            status_text = Text(f"{icon} {status.value}", style=style)
        elif row.id_documento == current_id:
            style = "bold cyan"
            status_text = Text("⏳ processando", style=style)
            evidencia = "..."
            msg = ""
        else:
            status_text = Text("—", style="dim")
            evidencia = ""
            msg = ""

        table.add_row(
            str(i),
            row.id_documento,
            row.municipio.value.title(),
            row.cnpj_raw,
            status_text,
            evidencia,
            msg,
        )

    return table


def _process_row(
    row: InputRow,
    connector: MunicipalConnector,
    evidencias_base: Path,
    db: Database,
    company_cache: dict[str, CompanyData],
) -> RowResult:
    company_dir, notes_dir = ensure_dirs(evidencias_base, row.municipio.value, row.cnpj_raw)
    now = datetime.now().isoformat(timespec="seconds")

    # --- 1. Decodifica a chave fiscal (offline, sem depender de portal) -------
    chave = decode_chave(row.cod_verificacao)
    cnpj_confere = None
    if chave.cnpj_emitente:
        cnpj_confere = "OK" if chave.cnpj_emitente == row.cnpj else "DIVERGE"

    # --- 2. Enriquece dados cadastrais da empresa via API pública -------------
    company = company_cache.get(row.cnpj)
    if company is None:
        company = fetch_company_data(row.cnpj)
        company_cache[row.cnpj] = company

    # --- 3. CCM: cache → conector (não exposto publicamente, registra tentativa)
    ccm_cached = db.get_ccm(row.municipio.value, row.cnpj)
    if ccm_cached:
        ccm_value = ccm_cached
        logger.info("{} | CCM em cache: {}", row.id_documento, ccm_value)
    else:
        ccm_result = connector.lookup_ccm(row)
        ccm_value = ccm_result.ccm if ccm_result.found else None
        db.set_ccm(
            row.municipio.value, row.cnpj, ccm_value,
            "SUCESSO" if ccm_result.found else "INDISPONIVEL",
        )

    # --- 4. Captura de evidência no portal (screenshot quando possível) -------
    reg_result = connector.download_company_registration(row, company_dir)
    inv_result = connector.download_invoice(row, notes_dir)

    # --- 5. Dados de apoio (sem gravar arquivos auxiliares) ------------------
    # O comprovante público (Receita) em PDF e o JSON da chave eram apenas apoio
    # e poluíam o output; o dado de apoio segue nas colunas da planilha/relatório,
    # mas não geramos mais arquivos. Mantém-se só cadastro municipal real + nota real.
    chave_decodificada = chave.tipo != TipoChave.MUNICIPAL_CURTO

    # --- 6. Status baseado no criterio do avaliador --------------------------
    cadastro_municipal_ok = reg_result.success and _has_file(reg_result.file_path, _CADASTRO_EXTS)
    nota_download_ok = inv_result.success and _has_file(inv_result.file_path, _NOTA_EXTS)
    notas = []
    if cadastro_municipal_ok:
        notas.append("cadastro municipal baixado")
    else:
        notas.append("cadastro municipal/CCM nao baixado")
    if ccm_value:
        notas.append(f"CCM encontrado: {ccm_value}")
    else:
        notas.append("CCM/Inscricao Municipal nao encontrado")
    if nota_download_ok:
        notas.append("nota fiscal PDF/XML baixada")
    else:
        notas.append("nota fiscal PDF/XML nao baixada")
    if company.found:
        notas.append(f"apoio: cadastro publico via {company.fonte}")
    if chave_decodificada:
        notas.append(f"apoio: {chave.descricao}")
    if cnpj_confere == "DIVERGE":
        notas.append("CNPJ emitente da chave diverge do fornecedor")
    portal_msg = "; ".join(filter(None, [reg_result.error, inv_result.error]))

    status = _classify_status(
        ccm_value=ccm_value,
        cadastro_municipal_ok=cadastro_municipal_ok,
        nota_download_ok=nota_download_ok,
    )

    msg = "; ".join(filter(None, notas + ([portal_msg] if portal_msg else [])))
    if not msg:
        msg = portal_msg or None

    logger.log(
        "SUCCESS" if status == StatusExecucao.SUCESSO else "WARNING",
        "{} | {} | {}", row.id_documento, status.value, msg or "ok",
    )

    db.log_execucao(
        id_documento=row.id_documento,
        municipio=row.municipio.value,
        cnpj=row.cnpj,
        status=status.value,
        mensagem=msg,
        arquivo_cadastro=reg_result.file_path,
        arquivo_nota_pdf=inv_result.file_path,
        estrategia=connector.estrategia,
    )

    inv_path = inv_result.file_path
    reg_path = reg_result.file_path
    return RowResult(
        id_documento=row.id_documento,
        status=status,
        mensagem_tecnica=msg,
        ccm_encontrado=ccm_value,
        razao_social=company.razao_social,
        situacao_cadastral=company.situacao_cadastral,
        atividade_principal=company.atividade_principal,
        fonte_cadastro=company.fonte,
        tipo_documento=chave.tipo.value,
        nota_municipio=chave.municipio or chave.uf,
        nota_numero=str(chave.numero) if chave.numero is not None else None,
        nota_competencia=chave.competencia,
        cnpj_emitente_confere=cnpj_confere,
        chave_dv_valido=(
            None if chave.dv_valido is None else ("valido" if chave.dv_valido else "invalido")
        ),
        arquivo_cadastro=reg_path if cadastro_municipal_ok else None,
        arquivo_cadastro_publico=None,
        arquivo_dados_nota=None,
        arquivo_nota_pdf=inv_path if nota_download_ok and inv_path and inv_path.endswith(".pdf") else None,
        arquivo_nota_xml=inv_path if nota_download_ok and inv_path and inv_path.endswith(".xml") else None,
        arquivo_evidencia_cadastro=(
            reg_path if reg_path and Path(reg_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".txt"} else None
        ),
        arquivo_evidencia_nota=(
            inv_path if inv_path and Path(inv_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".txt"} else None
        ),
        arquivo_evidencia=(
            inv_path if inv_path and Path(inv_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".txt"} else None
        ),
        municipio_estrategia=connector.estrategia,
        data_execucao=now,
    )


def _write_jsonl_line(log_file: Path, result: RowResult, row: "InputRow") -> None:
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "id_documento": result.id_documento,
        "municipio": row.municipio.value,
        "cnpj": row.cnpj_raw,
        "status": result.status.value,
        "mensagem_tecnica": result.mensagem_tecnica,
        "ccm_encontrado": result.ccm_encontrado,
        "razao_social": result.razao_social,
        "situacao_cadastral": result.situacao_cadastral,
        "atividade_principal": result.atividade_principal,
        "fonte_cadastro": result.fonte_cadastro,
        "tipo_documento": result.tipo_documento,
        "nota_municipio": result.nota_municipio,
        "nota_numero": result.nota_numero,
        "nota_competencia": result.nota_competencia,
        "cnpj_emitente_confere": result.cnpj_emitente_confere,
        "chave_dv_valido": result.chave_dv_valido,
        "arquivo_cadastro": result.arquivo_cadastro,
        "arquivo_cadastro_publico": result.arquivo_cadastro_publico,
        "arquivo_dados_nota": result.arquivo_dados_nota,
        "arquivo_nota_pdf": result.arquivo_nota_pdf,
        "arquivo_nota_xml": result.arquivo_nota_xml,
        "arquivo_evidencia_cadastro": result.arquivo_evidencia_cadastro,
        "arquivo_evidencia_nota": result.arquivo_evidencia_nota,
        "municipio_estrategia": result.municipio_estrategia,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(
    input_path: Path,
    output_dir: Path = Path("output"),
    evidencias_dir: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidencias = evidencias_dir or output_dir / "evidencias"
    evidencias.mkdir(parents=True, exist_ok=True)

    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = logs_dir / f"execution_{run_ts}.jsonl"

    db = Database(output_dir / "poc.db")
    results: dict[str, RowResult] = {}
    company_cache: dict[str, CompanyData] = {}

    rows = list(read_rows(input_path))
    total = len(rows)
    logger.info("Iniciando pipeline: {} linhas", total)

    with Live(console=console, refresh_per_second=4, vertical_overflow="visible") as live:
        for row in rows:
            live.update(_build_table(rows, results, row.id_documento))

            connector = _CONNECTORS.get(row.municipio)
            if not connector:
                logger.error("Sem conector para município: {}", row.municipio)
                result = RowResult(
                    id_documento=row.id_documento,
                    status=StatusExecucao.ERRO,
                    mensagem_tecnica=f"Município sem conector: {row.municipio}",
                )
                results[row.id_documento] = result
                _write_jsonl_line(jsonl_path, result, row)
                continue

            result = _process_row(row, connector, evidencias, db, company_cache)
            results[row.id_documento] = result
            _write_jsonl_line(jsonl_path, result, row)
            live.update(_build_table(rows, results, None))

    output_xlsx = output_dir / f"resultado_{run_ts}.xlsx"
    write_results(input_path, output_xlsx, results)

    sucesso = sum(1 for r in results.values() if r.status == StatusExecucao.SUCESSO)
    parcial = sum(1 for r in results.values() if r.status == StatusExecucao.PARCIAL)
    erro = sum(1 for r in results.values() if r.status == StatusExecucao.ERRO)

    console.print()
    console.rule("[bold cyan]Resultado Final[/bold cyan]")
    console.print(f"  [OK]  SUCESSO:    [bold green]{sucesso}/{total}[/bold green]")
    console.print(f"  [~]   PARCIAL:    [bold yellow]{parcial}/{total}[/bold yellow]")
    console.print(f"  [X]   ERRO:       [bold red]{erro}/{total}[/bold red]")
    console.print(f"  Planilha:         [cyan]{output_xlsx}[/cyan]")
    console.print(f"  Evidencias:       [cyan]{evidencias}[/cyan]")
    console.print(f"  Log JSONL:        [cyan]{jsonl_path}[/cyan]")

    from src.report import generate as generate_report
    report_path = generate_report(results, output_dir, output_xlsx, input_path)
    console.print(f"  Relatorio HTML:   [cyan]{report_path}[/cyan]")
    console.rule()

    logger.info("Pipeline concluído: {} sucesso | {} parcial | {} erro", sucesso, parcial, erro)
    return output_xlsx
