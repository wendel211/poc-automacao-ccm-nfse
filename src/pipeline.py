"""Orquestrador principal: lê planilha → processa por município → grava resultados."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Dict

from loguru import logger

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


def _process_row(
    row: InputRow,
    connector: MunicipalConnector,
    evidencias_base: Path,
    db: Database,
) -> RowResult:
    company_dir, notes_dir = ensure_dirs(evidencias_base, row.municipio.value, row.cnpj_raw)
    now = datetime.now().isoformat(timespec="seconds")

    # 1. CCM — usa cache se já consultado
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

    # 2. Cadastro municipal
    reg_result = connector.download_company_registration(row, company_dir)

    # 3. Nota fiscal
    inv_result = connector.download_invoice(row, notes_dir)

    # 4. Determina status final
    successes = [reg_result.success, inv_result.success]
    if all(successes):
        status = StatusExecucao.SUCESSO
        msg = None
    elif any(successes):
        status = StatusExecucao.PARCIAL
        msg = "; ".join(
            filter(None, [reg_result.error, inv_result.error])
        )
    else:
        status = StatusExecucao.ERRO
        msg = "; ".join(
            filter(None, [reg_result.error, inv_result.error])
        )

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
    logger.info("Iniciando pipeline: {} linhas", len(rows))

    for row in rows:
        connector = _CONNECTORS.get(row.municipio)
        if not connector:
            logger.error("Sem conector para município: {}", row.municipio)
            results[row.id_documento] = RowResult(
                id_documento=row.id_documento,
                status=StatusExecucao.ERRO,
                mensagem_tecnica=f"Município sem conector implementado: {row.municipio}",
            )
            continue
        results[row.id_documento] = _process_row(row, connector, evidencias, db)

    output_xlsx = output_dir / f"resultado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    write_results(input_path, output_xlsx, results)

    sucesso = sum(1 for r in results.values() if r.status == StatusExecucao.SUCESSO)
    parcial = sum(1 for r in results.values() if r.status == StatusExecucao.PARCIAL)
    erro = sum(1 for r in results.values() if r.status == StatusExecucao.ERRO)
    logger.info("Pipeline concluído: {} sucesso | {} parcial | {} erro", sucesso, parcial, erro)

    return output_xlsx
