export const getJSON = (url) => fetch(url).then((r) => r.json())

export const postJSON = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json())

export const deleteJSON = (url) => fetch(url, { method: 'DELETE' }).then((r) => r.json())

// 에이전트 SSE 스트림. onEvent(ev) 콜백, done/error에서 자동 종료.
export function runAgent(orderNo, onEvent) {
  const es = new EventSource(`/api/agent/run?order_no=${encodeURIComponent(orderNo)}`)
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data)
    onEvent(ev)
    if (ev.type === 'done' || ev.type === 'error') es.close()
  }
  es.onerror = () => es.close()
  return es
}

export const won = (n) => (n == null ? '-' : Math.round(n).toLocaleString('ko-KR'))
