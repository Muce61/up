#!/usr/bin/env python3
"""从 `reports/backtest` 现有文件生成单文件 HTML 报告。

只读取已有 Markdown / JSON / CSV，不重跑回测、不修改策略参数。
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_REPORT_ROOT = Path("reports/backtest")
DEFAULT_REVIEW_NAME = "etf_rotation_review.md"

KEY_METRICS = [
    "年化收益",
    "最大回撤",
    "Sharpe",
    "Sortino",
    "Calmar",
    "胜率",
    "盈亏比",
    "换手率",
    "交易次数",
]


@dataclass(frozen=True)
class ReportInputs:
    review_markdown: str
    review_path: Path | None
    json_files: tuple[Path, ...]
    csv_files: tuple[Path, ...]


def build_web_report(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    output_path: str | Path | None = None,
) -> Path:
    """生成本地静态 HTML，并返回输出路径。"""
    root = Path(report_root)
    output = Path(output_path) if output_path is not None else root / "index.html"
    inputs = _load_inputs(root)
    html_text = render_html(inputs, report_root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    return output


def render_html(inputs: ReportInputs, report_root: Path) -> str:
    conclusion = _extract_conclusion(inputs.review_markdown)
    provenance = _extract_provenance(inputs.review_markdown)
    metrics = _extract_key_metrics(inputs.review_markdown)
    review_body = markdown_to_html(inputs.review_markdown)
    json_summary = _render_json_file_summary(inputs.json_files)
    csv_summary = _render_csv_file_summary(inputs.csv_files)

    metric_cards = "\n".join(
        f"<div class=\"metric\"><span>{html.escape(name)}</span><strong>{html.escape(metrics.get(name, '未提供'))}</strong></div>"
        for name in KEY_METRICS
    )
    source_badge = "fixtures / 合成数据" if _is_fixture_based(provenance) else "真实快照或未明确"
    source_tone = "warning" if _is_fixture_based(provenance) else "neutral"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF 轮动回测报告</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --border: #d0d5dd;
      --accent: #1f5f8b;
      --warning: #8a4b0f;
      --danger: #9b1c1c;
      --ok: #17663a;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111315;
        --panel: #181b1f;
        --text: #e6e8eb;
        --muted: #a1a8b3;
        --border: #333842;
        --accent: #8ab4f8;
        --warning: #f0b35a;
        --danger: #ff8a8a;
        --ok: #7bd99f;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    h2 {{ font-size: 22px; margin: 30px 0 12px; border-top: 1px solid var(--border); padding-top: 22px; }}
    h3 {{ font-size: 18px; margin: 22px 0 10px; }}
    h4 {{ font-size: 16px; margin: 18px 0 8px; }}
    a {{ color: var(--accent); }}
    code {{ background: color-mix(in srgb, var(--border) 35%, transparent); padding: 1px 4px; border-radius: 4px; }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
    }}
    .meta {{ color: var(--muted); margin: 0; }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
    .badge {{
      display: inline-flex;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 13px;
      color: var(--muted);
    }}
    .badge.warning {{ color: var(--warning); border-color: color-mix(in srgb, var(--warning) 35%, var(--border)); }}
    .badge.danger {{ color: var(--danger); border-color: color-mix(in srgb, var(--danger) 35%, var(--border)); }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0 4px; }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px;
      min-height: 78px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 20px; }}
    .section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      margin: 18px 0;
      overflow-x: auto;
    }}
    .notice {{
      border-left: 4px solid var(--warning);
      padding: 10px 12px;
      background: color-mix(in srgb, var(--warning) 10%, transparent);
      margin: 16px 0;
    }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 18px; }}
    th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: color-mix(in srgb, var(--border) 28%, transparent); }}
    ul, ol {{ padding-left: 24px; }}
    .raw-report h1 {{ display: none; }}
    .footer {{ margin-top: 34px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 760px) {{
      main {{ padding: 20px 12px 40px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header class="hero">
    <h1>ETF 轮动策略回测网页报告</h1>
    <p class="meta">输入目录：<code>{html.escape(str(report_root))}</code>；输出文件：<code>reports/backtest/index.html</code></p>
    <div class="badge-row">
      <span class="badge danger">审查结论：{html.escape(conclusion)}</span>
      <span class="badge {source_tone}">数据来源：{html.escape(source_badge)}</span>
      <span class="badge">单文件静态 HTML</span>
      <span class="badge">未重跑回测</span>
    </div>
    <div class="notice">{html.escape(provenance or '未在报告中找到明确数据来源说明。')}</div>
  </header>

  <section>
    <h2>核心指标</h2>
    <div class="grid">
      {metric_cards}
    </div>
  </section>

  <section class="section">
    <h2>现有文件概览</h2>
    <p>本页面优先读取 <code>reports/backtest</code> 下已有 Markdown / JSON / CSV 文件生成。</p>
    <ul>
      <li>审查报告：{html.escape(str(inputs.review_path) if inputs.review_path else '未找到')}</li>
      <li>JSON 文件数：{len(inputs.json_files)}</li>
      <li>CSV 文件数：{len(inputs.csv_files)}</li>
    </ul>
    {json_summary}
    {csv_summary}
  </section>

  <section class="section raw-report">
    <h2>审查报告全文</h2>
    {review_body}
  </section>

  <p class="footer">生成方式：<code>python scripts/build_backtest_web_report.py</code>。本页面不包含外部依赖，不连接网络，不生成任何交易指令。</p>
</main>
</body>
</html>
"""


def _load_inputs(report_root: Path) -> ReportInputs:
    review_path = report_root / DEFAULT_REVIEW_NAME
    if review_path.exists():
        review_markdown = review_path.read_text(encoding="utf-8")
        selected_review: Path | None = review_path
    else:
        md_files = sorted(p for p in report_root.glob("*.md") if p.name != "index.md")
        selected_review = md_files[0] if md_files else None
        review_markdown = (
            selected_review.read_text(encoding="utf-8")
            if selected_review is not None
            else "# ETF 轮动策略回测报告\n\n未找到 Markdown 审查报告。"
        )
    json_files = tuple(sorted(p for p in report_root.rglob("*.json") if p.name != "index.json"))
    csv_files = tuple(sorted(report_root.rglob("*.csv")))
    return ReportInputs(
        review_markdown=review_markdown,
        review_path=selected_review,
        json_files=json_files,
        csv_files=csv_files,
    )


def _extract_conclusion(markdown: str) -> str:
    match = re.search(r"结论：\*\*([^*]+)\*\*", markdown)
    if match:
        return match.group(1).strip()
    match = re.search(r"三选一结论：\*\*([^*]+)\*\*", markdown)
    return match.group(1).strip() if match else "未明确"


def _extract_provenance(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("证据口径："):
            return _strip_markdown(line)
    return ""


def _extract_key_metrics(markdown: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [_strip_markdown(c.strip()) for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, value = cells[0], cells[1]
        if name in KEY_METRICS:
            metrics[name] = value
    return metrics


def markdown_to_html(markdown: str) -> str:
    """轻量 Markdown 渲染，覆盖本项目报告使用的标题、表格、列表和段落。"""
    lines = markdown.splitlines()
    html_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            html_parts.append(_render_markdown_table(table_lines))
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = _inline_markdown(heading.group(2))
            html_parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            html_parts.append("<ul>" + "".join(f"<li>{_inline_markdown(item)}</li>" for item in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            html_parts.append("<ol>" + "".join(f"<li>{_inline_markdown(item)}</li>" for item in items) + "</ol>")
            continue
        html_parts.append(f"<p>{_inline_markdown(stripped)}</p>")
        i += 1
    return "\n".join(html_parts)


def _render_markdown_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return ""
    header, body = rows[0], rows[1:]
    thead = "<thead><tr>" + "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in header) + "</tr></thead>"
    tbody = "<tbody>" + "".join(
        "<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    ) + "</tbody>"
    return f"<table>{thead}{tbody}</table>"


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _strip_markdown(text: str) -> str:
    return re.sub(r"[`*]", "", text).strip()


def _is_fixture_based(text: str) -> bool:
    low = text.lower()
    return "fixture" in low or "fixtures" in low or "合成" in text


def _render_json_file_summary(paths: Iterable[Path]) -> str:
    rows = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                summary = ", ".join(list(data.keys())[:6])
            else:
                summary = type(data).__name__
        except (OSError, json.JSONDecodeError) as exc:
            summary = f"读取失败：{exc}"
        rows.append([str(path), summary])
    if not rows:
        return "<p>未发现 JSON 回测归档。</p>"
    return _html_table(["JSON 文件", "摘要"], rows)


def _render_csv_file_summary(paths: Iterable[Path]) -> str:
    rows = []
    for path in paths:
        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, [])
                row_count = sum(1 for _ in reader)
            summary = f"{row_count} rows; columns: {', '.join(header[:8])}"
        except OSError as exc:
            summary = f"读取失败：{exc}"
        rows.append([str(path), summary])
    if not rows:
        return "<p>未发现 CSV 回测归档。</p>"
    return _html_table(["CSV 文件", "摘要"], rows)


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    thead = "<thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead>"
    tbody = "<tbody>" + "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    ) + "</tbody>"
    return f"<table>{thead}{tbody}</table>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local ETF backtest HTML report.")
    parser.add_argument("--report-root", default=str(DEFAULT_REPORT_ROOT))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    output = build_web_report(report_root=Path(args.report_root), output_path=args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
