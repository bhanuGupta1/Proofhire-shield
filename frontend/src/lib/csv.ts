// Minimal CSV parser: handles a header row, quoted fields, commas inside
// quotes, and escaped double-quotes (""). Good enough for pasted spreadsheet
// exports; not a full RFC-4180 implementation (no embedded newlines in quotes).
// ponytail: line-based; upgrade to a streaming parser only if imports grow huge.
export function parseCsv(text: string): Record<string, string>[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
  if (lines.length < 2) return []

  const parseLine = (line: string): string[] => {
    const out: string[] = []
    let cur = ''
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"'
          i++
        } else if (ch === '"') {
          inQuotes = false
        } else {
          cur += ch
        }
      } else if (ch === '"') {
        inQuotes = true
      } else if (ch === ',') {
        out.push(cur)
        cur = ''
      } else {
        cur += ch
      }
    }
    out.push(cur)
    return out.map((c) => c.trim())
  }

  const headers = parseLine(lines[0]).map((h) => h.toLowerCase())
  return lines.slice(1).map((line) => {
    const cells = parseLine(line)
    const row: Record<string, string> = {}
    headers.forEach((h, i) => {
      row[h] = cells[i] ?? ''
    })
    return row
  })
}
