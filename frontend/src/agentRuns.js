import { reactive } from 'vue'

// 주문별 에이전트 실행 상태 — 모듈 스코프 reactive라서
// 주문 전환/탭 이동에도 유지되고, 여러 주문 동시 실행을 지원한다.
// runs[order_no] = { running, events, picks, candCount, market, carrierState,
//                    rec, rfqTotal, rfqReplied, threads }
export const runs = reactive({})

export function initRun(orderNo) {
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
