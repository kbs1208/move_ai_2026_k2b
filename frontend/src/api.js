export const getJSON = (url) => fetch(url).then((r) => r.json())

export const postJSON = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json())

export const deleteJSON = (url) => fetch(url, { method: 'DELETE' }).then((r) => r.json())

export const won = (n) => (n == null ? '-' : Math.round(n).toLocaleString('ko-KR'))

// 초경량 마크다운 렌더러 (근거 텍스트용: 소제목/굵게/목록/문단)
export function md(src) {
  if (!src) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
  return src.split('\n').map((line) => {
    const h = line.match(/^\s*#{1,4}\s+(.*)$/)
    if (h) return `<h4>${inline(h[1])}</h4>`
    const li = line.match(/^\s*[-•]\s+(.*)$/)
    if (li) return `<p class="md-li">• ${inline(li[1])}</p>`
    const ol = line.match(/^\s*(\d+)\.\s+(.*)$/)
    if (ol) return `<p class="md-li">${ol[1]}. ${inline(ol[2])}</p>`
    if (!line.trim()) return '<div class="md-gap"></div>'
    return `<p>${inline(line)}</p>`
  }).join('')
}
