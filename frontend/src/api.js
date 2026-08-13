export const getJSON = (url) => fetch(url).then((r) => r.json())

export const postJSON = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json())

export const deleteJSON = (url) => fetch(url, { method: 'DELETE' }).then((r) => r.json())

export const won = (n) => (n == null ? '-' : Math.round(n).toLocaleString('ko-KR'))

// 초경량 마크다운 렌더러 (근거 텍스트용: 소제목/굵게/목록/문단/테이블)
export function md(src) {
  if (!src) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
  const isRow = (l) => /^\s*\|.*\|\s*$/.test(l)
  const isSep = (cells) => cells.every((c) => /^:?-{2,}:?$/.test(c))
  const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())

  const lines = src.split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // 마크다운 테이블 블록
    if (isRow(line)) {
      const rows = []
      while (i < lines.length && isRow(lines[i])) {
        const cs = cells(lines[i])
        if (!isSep(cs)) rows.push(cs)
        i++
      }
      if (rows.length) {
        const [head, ...body] = rows
        out.push(
          '<table class="md-table"><thead><tr>' +
          head.map((c) => `<th>${inline(c)}</th>`).join('') +
          '</tr></thead><tbody>' +
          body.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') +
          '</tbody></table>'
        )
      }
      continue
    }
    const h = line.match(/^\s*#{1,4}\s+(.*)$/)
    if (h) out.push(`<h4>${inline(h[1])}</h4>`)
    else {
      const li = line.match(/^\s*[-•]\s+(.*)$/)
      const ol = line.match(/^\s*(\d+)\.\s+(.*)$/)
      if (li) out.push(`<p class="md-li">• ${inline(li[1])}</p>`)
      else if (ol) out.push(`<p class="md-li">${ol[1]}. ${inline(ol[2])}</p>`)
      else if (!line.trim()) out.push('<div class="md-gap"></div>')
      else out.push(`<p>${inline(line)}</p>`)
    }
    i++
  }
  return out.join('')
}
