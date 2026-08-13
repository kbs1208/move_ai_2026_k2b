import { reactive, ref } from 'vue'
import { postJSON } from './api.js'

// 주문별 에이전트 실행 상태 — 서버가 브로드캐스트하는 전역 SSE(/api/events)로 채워진다.
// 모든 접속자(브라우저)가 동일한 실행 상태를 실시간으로 본다.
export const runs = reactive({})
// 주문/대시보드 데이터 변경 신호 (추천/예약/취소 발생 시 증가 -> 화면에서 재조회)
export const dataVersion = ref(0)

function initSlot(orderNo) {
  runs[orderNo] = {
    running: true,
    events: [],
    picks: [],
    candCount: 0,
    market: null,
    carrierState: {},   // carrier -> {std, quote, last, decision}
    rec: null,
    rfqTotal: 0,        // 발송한 RFQ 수 (최대 모수)
    rfqReplied: 0,      // 수신한 RFQ 회신 수
    threads: {},        // carrier -> thread (네고 메일 내역)
  }
  return runs[orderNo]
}

function reduce(slot, ev) {
  if (ev.message) slot.events.push(ev)
  if (ev.type === 'start') {
    slot.running = true
  } else if (ev.type === 'candidates') {
    slot.candCount = ev.candidates.length
    slot.picks = ev.picks
    slot.rfqTotal = ev.picks.length
    for (const p of ev.picks) slot.carrierState[p.carrier] = { std: p.std.allin_per_kg }
  } else if (ev.type === 'email') {
    slot.threads[ev.thread.carrier] = ev.thread
    if (ev.stage === 'rfq' && ev.direction === 'in') slot.rfqReplied++
  } else if (ev.type === 'quotes') {
    slot.market = ev.market
    for (const [c, q] of Object.entries(ev.market.quotes))
      slot.carrierState[c] = { ...slot.carrierState[c], quote: q, last: q }
  } else if (ev.type === 'nego') {
    slot.carrierState[ev.carrier] = {
      ...slot.carrierState[ev.carrier], last: ev.rate, decision: ev.decision,
    }
  } else if (ev.type === 'recommendation') {
    slot.rec = ev.recommendation
    dataVersion.value++
  } else if (ev.type === 'done' || ev.type === 'error') {
    slot.running = false
    dataVersion.value++
  }
}

function apply(ev) {
  if (ev.type === 'snapshot') {
    // 접속(재접속) 시 서버 상태로 재구성 — 진행 중이던 실행도 이어서 보임
    for (const k of Object.keys(runs)) delete runs[k]
    for (const [no, r] of Object.entries(ev.runs || {})) {
      const slot = initSlot(no)
      slot.running = r.running
      for (const e of r.events) reduce(slot, e)
      slot.running = r.running
    }
    dataVersion.value++
    return
  }
  if (ev.type === 'booked') {
    dataVersion.value++
    return
  }
  if (ev.type === 'cancelled') {
    delete runs[ev.order_no] // 타임라인/견적/추천 화면 제거 (전 접속자)
    dataVersion.value++
    return
  }
  const no = ev.order_no
  if (!no) return
  if (!runs[no]) initSlot(no)
  reduce(runs[no], ev)
}

// 전역 SSE 연결 (모듈 로드 시 1회, 끊기면 EventSource가 자동 재접속 -> 스냅샷으로 복원)
const es = new EventSource('/api/events')
es.onmessage = (e) => apply(JSON.parse(e.data))

export async function startAgent(orderNo) {
  await postJSON(`/api/agent/start?order_no=${encodeURIComponent(orderNo)}`, {})
}
