from __future__ import annotations

import html
import re


def render_html_report(markdown: str) -> str:
    body_lines: list[str] = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        escaped = html.escape(line)
        if line.startswith("# "):
            body_lines.append(f"<h1>{_inline_code(escaped[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{_inline_code(escaped[3:])}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{_inline_code(escaped[4:])}</h3>")
        elif line.startswith("#### "):
            body_lines.append(f"<h4>{_inline_code(escaped[5:])}</h4>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{_inline_code(escaped[2:])}</li>")
        elif line.startswith("| "):
            table_lines = [line]
            index += 1
            while index < len(lines) and lines[index].startswith("| "):
                table_lines.append(lines[index])
                index += 1
            body_lines.append(_table_html(table_lines))
            continue
        elif not line.strip():
            body_lines.append("")
        else:
            body_lines.append(f"<p>{_inline_code(escaped)}</p>")
        index += 1

    body = "\n".join(body_lines)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>多轮对话评测报告</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2937; background: #f8fafc; }}
    h1, h2, h3 {{ color: #111827; }}
    h1 {{ margin-bottom: 20px; }}
    h2 {{ margin-top: 28px; border-left: 4px solid #2563eb; padding-left: 10px; }}
    pre {{ background: #f3f4f6; padding: 8px; border-radius: 6px; overflow-x: auto; }}
    li {{ margin: 6px 0; }}
    p, li {{ line-height: 1.6; }}
    code {{ background: #eef2ff; padding: 2px 4px; border-radius: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 14px 0 20px; background: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08); }}
    th {{ background: #dbeafe; color: #1e3a8a; text-align: left; padding: 12px 14px; font-size: 14px; }}
    td {{ padding: 12px 14px; border-top: 1px solid #e5e7eb; font-size: 14px; }}
    tr:nth-child(even) td {{ background: #f8fafc; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def _inline_code(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def _table_html(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [html.escape(cell.strip()) for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return "\n".join(f"<pre>{' | '.join(row)}</pre>" for row in rows)

    header = rows[0]
    body = rows[2:] if len(rows) >= 3 else []
    head_html = "".join(f"<th>{_inline_code(cell)}</th>" for cell in header)
    body_html = "".join(
        "<tr>{}</tr>".format("".join(f"<td>{_inline_code(cell)}</td>" for cell in row))
        for row in body
    )
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"
