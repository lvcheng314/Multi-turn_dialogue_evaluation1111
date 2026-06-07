export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function renderInlineMarkdown(text: string): string {
  let html = escapeHtml(text)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m: string, label: string, href: string) => {
    const safeHref = href.replace(/"/g, "%22")
    return '<a href="' + safeHref + '" target="_blank" rel="noreferrer">' + label + "</a>"
  })
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>")
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
  return html
}

function renderMarkdownTable(rows: string[][]): string {
  if (!rows.length) return ""
  const [header, ...body] = rows
  return [
    "<table>",
    "<thead><tr>",
    ...header.map((cell) => "<th>" + renderInlineMarkdown(cell.trim()) + "</th>"),
    "</tr></thead>",
    "<tbody>",
    ...body.map(
      (row) =>
        "<tr>" + row.map((cell) => "<td>" + renderInlineMarkdown(cell.trim()) + "</td>").join("") + "</tr>"
    ),
    "</tbody>",
    "</table>",
  ].join("")
}

export function renderMarkdown(text: string): string {
  const normalized = text.replace(/\r\n/g, "\n").trim()
  if (!normalized) return ""

  const lines = normalized.split("\n")
  const blocks: string[] = []
  let paragraph: string[] = []
  let bulletItems: string[] | null = null
  let orderedItems: string[] | null = null
  let quoteLines: string[] | null = null
  let tableLines: string[] | null = null
  let inCodeBlock = false
  let codeLang = ""
  let codeLines: string[] = []

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push("<p>" + paragraph.map((l) => renderInlineMarkdown(l)).join("<br>") + "</p>")
    paragraph = []
  }
  const flushBullets = () => {
    if (!bulletItems?.length) return
    blocks.push("<ul>" + bulletItems.map((item) => "<li>" + renderInlineMarkdown(item) + "</li>").join("") + "</ul>")
    bulletItems = null
  }
  const flushOrdered = () => {
    if (!orderedItems?.length) return
    blocks.push("<ol>" + orderedItems.map((item) => "<li>" + renderInlineMarkdown(item) + "</li>").join("") + "</ol>")
    orderedItems = null
  }
  const flushQuote = () => {
    if (!quoteLines?.length) return
    blocks.push("<blockquote><p>" + quoteLines.map((l) => renderInlineMarkdown(l)).join("<br>") + "</p></blockquote>")
    quoteLines = null
  }
  const flushTable = () => {
    if (!tableLines?.length || tableLines.length < 2) {
      tableLines = null
      return
    }
    const rawRows = tableLines
      .filter((_line, i) => i !== 1)
      .map((line) => line.split("|").slice(1, -1))
    blocks.push(renderMarkdownTable(rawRows))
    tableLines = null
  }
  const flushAll = () => {
    flushParagraph()
    flushBullets()
    flushOrdered()
    flushQuote()
    flushTable()
  }

  for (const line of lines) {
    if (line.startsWith("```")) {
      flushAll()
      if (inCodeBlock) {
        const langAttr = codeLang ? ' data-lang="' + escapeHtml(codeLang) + '"' : ""
        blocks.push(
          '<pre class="md-code"' + langAttr + "><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>"
        )
        inCodeBlock = false
        codeLang = ""
        codeLines = []
      } else {
        inCodeBlock = true
        codeLang = line.slice(3).trim()
      }
      continue
    }
    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }
    if (!line.trim()) {
      flushAll()
      continue
    }

    if (/^\|.+\|$/.test(line.trim())) {
      flushParagraph()
      flushBullets()
      flushOrdered()
      flushQuote()
      tableLines ??= []
      tableLines.push(line.trim())
      continue
    }
    if (tableLines && /^(\|\s*[-:]+\s*)+\|$/.test(line.trim())) {
      tableLines.push(line.trim())
      continue
    }
    if (tableLines) {
      flushTable()
    }

    const hrMatch = line.match(/^\s*([-*_])(?:\s*\1){2,}\s*$/)
    if (hrMatch) {
      flushAll()
      blocks.push("<hr>")
      continue
    }

    const headingMatch = line.match(/^\s*(#{1,4})\s+(.+)$/)
    if (headingMatch) {
      flushAll()
      blocks.push(
        "<h" + headingMatch[1].length + ">" + renderInlineMarkdown(headingMatch[2].trim()) + "</h" + headingMatch[1].length + ">"
      )
      continue
    }
    const quoteMatch = line.match(/^>\s?(.*)$/)
    if (quoteMatch) {
      flushParagraph()
      flushBullets()
      flushOrdered()
      quoteLines ??= []
      quoteLines.push(quoteMatch[1])
      continue
    }
    const bulletMatch = line.match(/^[-*]\s+(.+)$/)
    if (bulletMatch) {
      flushParagraph()
      flushOrdered()
      flushQuote()
      bulletItems ??= []
      bulletItems.push(bulletMatch[1].trim())
      continue
    }
    const orderedMatch = line.match(/^\d+\.\s+(.+)$/)
    if (orderedMatch) {
      flushParagraph()
      flushBullets()
      flushQuote()
      orderedItems ??= []
      orderedItems.push(orderedMatch[1].trim())
      continue
    }
    paragraph.push(line.trim())
  }

  if (inCodeBlock) {
    const langAttr = codeLang ? ' data-lang="' + escapeHtml(codeLang) + '"' : ""
    blocks.push(
      '<pre class="md-code"' + langAttr + "><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>"
    )
  } else {
    flushAll()
  }

  return blocks.join("")
}
