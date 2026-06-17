"""Orquestrador principal: lê planilha → processa por município → grava resultados."""
from __future__ import annotations
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
    StatusExecucao.SUCESSO: "✅",
    StatusExecucao.PARCIAL: "⚠️ ",
    StatusExecucao.ERRO: "❌",
    StatusExecucao.INDISPONIVEL: "—",
}

console = Console()


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
            evidencia = "sim" if (result.arquivo_cadastro or result.arquivo_evidencia or result.arquivo_nota_pdf) else "nao"
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
) -> RowResult:
    company_dir, notes_dir = ensure_dirs(evidencias_base, row.municipio.value, row.cnpj_raw)
    now = datetime.now().isoformat(timespec="seconds")

    ccm_cached = db.get_ccm(row.municipio.value, row.cnpj)
    if ccm_cached:
        ccm_value = ccm_cached
        logger.info("{} | CCM em cache: {}", row.id_documento, ccm_value)
    else:
        ccm_result = connector.lookup_ccm(row)
        ccm_value = ccm_result.ccm if ccm_result.found else None
        db.set_ccm(
            row.municipio.value,
            row.cnpj,
            ccm_value,
            "SUCESSO" if ccm_result.found else "INDISPONIVEL",
        )

    reg_result = connector.download_company_registration(row, company_dir)
    inv_result = connector.download_invoice(row, notes_dir)

    successes = [reg_result.success, inv_result.success]
    if all(successes):
        status = StatusExecucao.SUCESSO
        msg = None
    elif any(successes):
        status = StatusExecucao.PARCIAL
        msg = "; ".join(filter(None, [reg_result.error, inv_result.error]))
    else:
        status = StatusExecucao.ERRO
        msg = "; ".join(filter(None, [reg_result.error, inv_result.error]))

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
    return RowResult(
        id_documento=row.id_documento,
        status=status,
        mensagem_tecnica=msg,
        ccm_encontrado=ccm_value,
        arquivo_cadastro=reg_result.file_path,
        arquivo_nota_pdf=inv_path if inv_path and inv_path.endswith(".pdf") else None,
        arquivo_nota_xml=inv_path if inv_path and inv_path.endswith(".xml") else None,
        arquivo_evidencia=inv_path if inv_path and inv_path.endswith(".png") else None,
        municipio_estrategia=connector.estrategia,
        data_execucao=now,
    )


def run(
    input_path: Path,
    output_dir: Path = Path("output"),
    evidencias_dir: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidencias = evidencias_dir or output_dir / "evidencias"
    evidencias.mkdir(parents=True, exist_ok=True)

    db = Database(output_dir / "poc.db")
    results: dict[str, RowResult] = {}

    rows = list(read_rows(input_path))
    total = len(rows)
    logger.info("Iniciando pipeline: {} linhas", total)

    with Live(console=console, refresh_per_second=4, vertical_overflow="visible") as live:
        for row in rows:
            live.update(_build_table(rows, results, row.id_documento))

            connector = _CONNECTORS.get(row.municipio)
            if not connector:
                logger.error("Sem conector para município: {}", row.municipio)
                results[row.id_documento] = RowResult(
                    id_documento=row.id_documento,
                    status=StatusExecucao.ERRO,
                    mensagem_tecnica=f"Município sem conector: {row.municipio}",
                )
                continue

            results[row.id_documento] = _process_row(row, connector, evidencias, db)
            live.update(_build_table(rows, results, None))

    output_xlsx = output_dir / f"resultado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    write_results(input_path, output_xlsx, results)

    sucesso = sum(1 for r in results.values() if r.status == StatusExecucao.SUCESSO)
    parcial = sum(1 for r in results.values() if r.status == StatusExecucao.PARCIAL)
    erro = sum(1 for r in results.values() if r.status == StatusExecucao.ERRO)

    console.print()
    console.rule("[bold cyan]Resultado Final[/bold cyan]")
    console.print(f"  ✅ SUCESSO:      [bold green]{sucesso}/{total}[/bold green]")
    console.print(f"  ⚠️  PARCIAL:      [bold yellow]{parcial}/{total}[/bold yellow]")
    console.print(f"  ❌ ERRO:         [bold red]{erro}/{total}[/bold red]")
    console.print(f"  📄 Planilha:     [cyan]{output_xlsx}[/cyan]")
    console.print(f"  📁 Evidências:   [cyan]{evidencias}[/cyan]")

    from src.report import generate as generate_report
    report_path = generate_report(results, output_dir, output_xlsx, input_path)
    console.print(f"  🌐 Relatório:    [cyan]{report_path}[/cyan]")
    console.rule()

    logger.info("Pipeline concluído: {} sucesso | {} parcial | {} erro", sucesso, parcial, erro)
    return output_xlsx
