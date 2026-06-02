from __future__ import annotations

import html
import re


def render_html_report(markdown: str) -> str:
    body_lines: list[str] = []
    for line in markdown.splitlines():
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
            body_lines.append(f"<pre>{escaped}</pre>")
        elif not line.strip():
            body_lines.append("")
        else:
            body_lines.append(f"<p>{_inline_code(escaped)}</p>")

    body = "\n".join(body_lines)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>多轮对话评测报告</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2937; }}
    h1, h2, h3 {{ color: #111827; }}
    pre {{ background: #f3f4f6; padding: 8px; border-radius: 6px; overflow-x: auto; }}
    li {{ margin: 6px 0; }}
    code {{ background: #eef2ff; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def _inline_code(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
