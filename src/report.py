"""Gerador de relatório HTML ao final da execução do pipeline."""
from __future__ import annotations
import base64
from datetime import datetime
from pathlib import Path

from src.models import RowResult, StatusExecucao

_STATUS_COLOR = {
    StatusExecucao.SUCESSO: "#C6EFCE",
    StatusExecucao.PARCIAL: "#FFEB9C",
    StatusExecucao.ERRO: "#FFC7CE",
    StatusExecucao.INDISPONIVEL: "#E0E0E0",
}

_STATUS_ICON = {
    StatusExecucao.SUCESSO: "✅",
    StatusExecucao.PARCIAL: "⚠️",
    StatusExecucao.ERRO: "❌",
    StatusExecucao.INDISPONIVEL: "—",
}


def _embed_image(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".png":
        return ""
    data = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" style="max-width:320px;max-height:200px;border:1px solid #ccc;border-radius:4px;cursor:pointer" onclick="this.style.maxWidth=this.style.maxWidth===\'100%\'?\'320px\':\'100%\'">'


def _row_html(row_result: RowResult, index: int) -> str:
    r = row_result
    color = _STATUS_COLOR.get(r.status, "#fff")
    icon = _STATUS_ICON.get(r.status, "")
    cadastro_img = _embed_image(r.arquivo_evidencia_cadastro)
    nota_img = _embed_image(r.arquivo_evidencia_nota or r.arquivo_evidencia)
    msg = (r.mensagem_tecnica or "—").replace("—", " - ")
    return f"""
    <tr style="background:{color}">
      <td style="text-align:center">{index}</td>
      <td><code>{r.id_documento}</code></td>
      <td>{icon} <strong>{r.status.value}</strong></td>
      <td><code>{r.ccm_encontrado or "—"}</code></td>
      <td style="font-size:0.8em;max-width:260px;word-break:break-word">{msg}</td>
      <td style="text-align:center">{cadastro_img or "—"}</td>
      <td style="text-align:center">{nota_img or "—"}</td>
    </tr>"""


def generate(
    results: dict[str, RowResult],
    output_dir: Path,
    xlsx_path: Path,
    input_path: Path,
) -> Path:
    total = len(results)
    sucesso = sum(1 for r in results.values() if r.status == StatusExecucao.SUCESSO)
    parcial = sum(1 for r in results.values() if r.status == StatusExecucao.PARCIAL)
    erro = sum(1 for r in results.values() if r.status == StatusExecucao.ERRO)
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    rows_html = "".join(
        _row_html(r, i) for i, r in enumerate(results.values(), 1)
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatório POC CCM + NFS-e</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
    header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 2rem; }}
    header h1 {{ font-size: 1.6rem; }}
    header p {{ opacity: .7; font-size: 0.9rem; margin-top: .3rem; }}
    .summary {{ display: flex; gap: 1rem; padding: 1.5rem 2rem; flex-wrap: wrap; }}
    .card {{ background: white; border-radius: 8px; padding: 1.2rem 2rem; flex: 1; min-width: 140px;
             box-shadow: 0 2px 6px rgba(0,0,0,.08); text-align: center; }}
    .card .value {{ font-size: 2.2rem; font-weight: 700; }}
    .card .label {{ font-size: 0.8rem; color: #888; margin-top: .2rem; }}
    .green {{ color: #2e7d32; }} .yellow {{ color: #f57f17; }} .red {{ color: #c62828; }} .blue {{ color: #1565c0; }}
    .content {{ padding: 0 2rem 2rem; }}
    .meta {{ background: white; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1rem;
             box-shadow: 0 2px 6px rgba(0,0,0,.08); font-size: 0.85rem; color: #555; }}
    .meta a {{ color: #1565c0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px;
             overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,.08); font-size: 0.85rem; }}
    th {{ background: #1a1a2e; color: white; padding: .8rem 1rem; text-align: left; font-weight: 600; }}
    td {{ padding: .7rem 1rem; border-bottom: 1px solid rgba(0,0,0,.05); vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    code {{ background: #f0f0f0; padding: .1rem .4rem; border-radius: 3px; font-size: .8rem; }}
    footer {{ text-align: center; padding: 1.5rem; color: #aaa; font-size: .8rem; }}
  </style>
</head>
<body>
  <header>
    <h1>📊 Relatório de Execução — POC CCM + NFS-e</h1>
    <p>Gerado em {now} &nbsp;|&nbsp; Entrada: {input_path.name}</p>
  </header>

  <div class="summary">
    <div class="card"><div class="value blue">{total}</div><div class="label">Total de Linhas</div></div>
    <div class="card"><div class="value green">{sucesso}</div><div class="label">✅ Sucesso</div></div>
    <div class="card"><div class="value yellow">{parcial}</div><div class="label">⚠️ Parcial</div></div>
    <div class="card"><div class="value red">{erro}</div><div class="label">❌ Erro</div></div>
  </div>

  <div class="content">
    <div class="meta">
      📄 Planilha de saída: <a href="{xlsx_path.name}">{xlsx_path.name}</a>
      &nbsp;|&nbsp; 📁 Evidências em: <code>evidencias/</code>
    </div>

    <table>
      <thead>
        <tr>
          <th>#</th><th>ID Documento</th><th>Status</th><th>CCM</th>
          <th>Mensagem</th><th>Evidencia Cadastro</th><th>Evidencia Nota</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <footer>POC Automação CCM + NFS-e &nbsp;|&nbsp; {now}</footer>
</body>
</html>"""

    out = output_dir / f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out.write_text(html, encoding="utf-8")
    return out
