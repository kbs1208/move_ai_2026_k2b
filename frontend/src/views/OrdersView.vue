<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { deleteJSON, getJSON, postJSON, runAgent, won } from '../api.js'

const orders = ref([])
const selected = ref(null)
const running = ref(false)
const events = ref([])
const picks = ref([])
const candCount = ref(0)
const market = ref(null)
const carrierState = ref({}) // code -> {std, quote, last, decision}
const rec = ref(null)        // 이번 실행 추천
const booking = ref(false)
const logBox = ref(null)

async function loadOrders(keepSel = false) {
  const no = selected.value?.order_no
  orders.value = await getJSON('/api/orders')
  if (keepSel && no) selected.value = orders.value.find((o) => o.order_no === no) || null
}
onMounted(loadOrders)

// 화면에 보여줄 추천: 이번 실행 결과 우선, 없으면 DB에 저장된 과거 실행 결과
const shownRec = computed(() => rec.value || selected.value?.recommendation || null)
const selStatus = computed(() =>
  orders.value.find((o) => o.order_no === shownRec.value?.order_no)?.status
)

function select(o) {
  if (running.value) return
  selected.value = o
  events.value = []
  picks.value = []
  market.value = null
  carrierState.value = {}
  rec.value = null
}

function pushLog(ev) {
  if (ev.message) events.value.push(ev)
  nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
}

function run() {
  if (!selected.value) return
  running.value = true
  events.value = []
  rec.value = null
  market.value = null
  carrierState.value = {}
  runAgent(selected.value.order_no, (ev) => {
    pushLog(ev)
    if (ev.type === 'candidates') {
      candCount.value = ev.candidates.length
      picks.value = ev.picks
      for (const p of ev.picks) carrierState.value[p.carrier] = { std: p.std.allin_per_kg }
    } else if (ev.type === 'quotes') {
      market.value = ev.market
      for (const [c, q] of Object.entries(ev.market.quotes))
        carrierState.value[c] = { ...carrierState.value[c], quote: q, last: q }
    } else if (ev.type === 'nego') {
      carrierState.value[ev.carrier] = {
        ...carrierState.value[ev.carrier], last: ev.rate, decision: ev.decision,
      }
    } else if (ev.type === 'recommendation') {
      rec.value = ev.recommendation
    } else if (ev.type === 'done' || ev.type === 'error') {
      running.value = false
      loadOrders(true) // 저장된 추천/상태 반영
    }
  })
}

async function confirmBooking() {
  booking.value = true
  await postJSON('/api/bookings', shownRec.value)
  await loadOrders(true)
  booking.value = false
}

async function cancelBooking() {
  booking.value = true
  await deleteJSON(`/api/bookings/${selected.value.order_no}`)
  await loadOrders(true) // 서버 상태(DB) 기준 재동기화 — 새로고침 없이도 반영
  booking.value = false
}

const icons = {
  start: '▶', candidates: '🔍', history: '📊', progress: '…', email: '✉',
  quotes: '💰', nego: '🤝', recommendation: '★', done: '✔', error: '✖',
}
const fmt = (n, d = 2) => (n == null ? '-' : Number(n).toLocaleString('ko-KR', { maximumFractionDigits: d }))
</script>

<template>
  <div class="wrap">
    <h2>KD 주문 정보 <span class="sub">주문을 선택하고 AI 에이전트를 실행하세요</span></h2>
    <div class="panel table-box">
      <table>
        <thead>
          <tr>
            <th>주문번호</th><th>구간</th><th>품목</th><th class="num">CW (kg)</th>
            <th>DG</th><th>준비일</th><th>희망도착</th><th>데드라인</th><th>상태</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.order_no"
              :class="{ sel: selected?.order_no === o.order_no }" @click="select(o)">
            <td class="mono">{{ o.order_no }}</td>
            <td>{{ o.origin }} → {{ o.dest }}</td>
            <td class="item">{{ o.item_name }}</td>
            <td class="num">{{ won(o.chargeable_weight_kg) }}</td>
            <td><span v-if="o.is_dg" class="badge amber">DG</span><span v-else class="badge gray">-</span></td>
            <td>{{ o.cargo_ready_date }}</td>
            <td>{{ o.desired_arr_date }}</td>
            <td><b>{{ o.deadline_date }}</b></td>
            <td>
              <span :class="['badge', o.status === 'BOOKED' ? 'green' : 'blue']">{{ o.status }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 주문 상세 -->
    <section v-if="selected" class="panel pad detail">
      <div class="detail-head">
        <h3>주문 상세 <span class="mono sub">{{ selected.order_no }}</span></h3>
        <button v-if="selected.status === 'BOOKED'" class="danger" :disabled="booking" @click="cancelBooking">
          {{ booking ? '취소 중...' : '예약 취소' }}
        </button>
        <button v-else class="primary" :disabled="running" @click="run">
          {{ running ? 'AI 에이전트 실행 중...' : 'AI 에이전트 실행' }}
        </button>
      </div>
      <div class="info-grid">
        <div class="info"><label>구간</label><b>{{ selected.origin }} → {{ selected.dest }}</b></div>
        <div class="info"><label>품목</label><b>{{ selected.item_name }}</b></div>
        <div class="info"><label>위험물(DG)</label>
          <b><span v-if="selected.is_dg" class="badge amber">DG — 화물기만 가능</span><span v-else>일반 화물</span></b></div>
        <div class="info"><label>상태</label>
          <b><span :class="['badge', selected.status === 'BOOKED' ? 'green' : 'blue']">{{ selected.status }}</span></b></div>
        <div class="info"><label>화물 준비일</label><b>{{ selected.cargo_ready_date }}</b></div>
        <div class="info"><label>희망 도착일</label><b>{{ selected.desired_arr_date }}</b></div>
        <div class="info"><label>데드라인</label><b class="red">{{ selected.deadline_date }}</b></div>
        <div class="info"><label>총 수량</label><b>{{ selected.pieces }} pcs</b></div>
        <div class="info"><label>실중량 (GW)</label><b>{{ fmt(selected.gross_weight_kg) }} kg</b></div>
        <div class="info"><label>청구중량 (CW)</label><b>{{ fmt(selected.chargeable_weight_kg) }} kg</b></div>
        <div class="info"><label>최대 높이</label><b>{{ fmt(selected.max_height_cm, 0) }} cm</b></div>
      </div>
      <table class="lines">
        <thead>
          <tr><th>#</th><th>품목</th><th>DG</th><th class="num">수량</th><th class="num">가로(cm)</th><th class="num">세로(cm)</th>
              <th class="num">높이(cm)</th><th class="num">실중량(kg)</th><th class="num">CBM</th><th class="num">CW(kg)</th></tr>
        </thead>
        <tbody>
          <tr v-for="(l, i) in selected.lines" :key="i">
            <td>{{ i + 1 }}</td>
            <td class="item">{{ l.item_name }}</td>
            <td><span v-if="l.is_dg" class="badge amber">DG</span><span v-else class="badge gray">-</span></td>
            <td class="num">{{ l.piece }}</td>
            <td class="num">{{ fmt(l.width, 0) }}</td>
            <td class="num">{{ fmt(l.length, 0) }}</td>
            <td class="num">{{ fmt(l.height, 0) }}</td>
            <td class="num">{{ fmt(l.weight_kg) }}</td>
            <td class="num">{{ fmt(l.cbm) }}</td>
            <td class="num"><b>{{ fmt(l.cw) }}</b></td>
          </tr>
        </tbody>
      </table>
      <div class="cw-note sub">CW = max(실중량, 가로×세로×높이/6,000×수량) — 라인 합산 {{ fmt(selected.chargeable_weight_kg) }}kg 적용</div>
    </section>

    <div v-if="events.length" class="grid">
      <section class="panel pad">
        <h3>에이전트 타임라인</h3>
        <div class="log" ref="logBox">
          <div v-for="(ev, i) in events" :key="i" :class="['log-line', ev.type]">
            <span class="log-icon">{{ icons[ev.type] || '·' }}</span>{{ ev.message }}
          </div>
        </div>
      </section>

      <section class="panel pad">
        <h3>항공사별 견적 · 네고 현황 <span v-if="candCount" class="sub">(운항 후보 {{ candCount }}편)</span></h3>
        <table>
          <thead>
            <tr><th>항공사 / 편</th><th>출발일</th><th>도착</th><th class="num">표준가</th><th class="num">첫 견적</th>
                <th class="num">최종가</th><th>안전성</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in picks" :key="p.carrier"
                :class="{ winner: rec && rec.carrier === p.carrier }">
              <td><b>{{ p.airline_name }}</b> <span class="mono sub">{{ p.flight_number }}</span>
                  <span :class="['badge', p.flight_type === 'CARGO' ? 'blue' : 'gray']">{{ p.flight_type === 'CARGO' ? '화물기' : '여객기' }}</span></td>
              <td>{{ p.dep_date }}</td>
              <td>{{ p.arr_date }} <span class="sub">{{ p.arr_time }}</span></td>
              <td class="num">{{ won(carrierState[p.carrier]?.std) }}</td>
              <td class="num">{{ won(carrierState[p.carrier]?.quote) }}</td>
              <td class="num"><b>{{ won(carrierState[p.carrier]?.last) }}</b>
                <span v-if="carrierState[p.carrier]?.decision === 'accept'" class="badge green">수락</span></td>
              <td>
                <span v-if="p.offload_safe" class="badge green">SAFE</span>
                <span v-else class="badge amber">RISK</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="market" class="market">
          시장 range: <b>kg당 {{ won(market.low) }} ~ {{ won(market.high) }}원</b> ({{ market.n }}개사 견적)
        </div>
      </section>
    </div>

    <!-- 추천 (이번 실행 or 저장된 결과) -->
    <section v-if="shownRec" class="rec">
      <div class="rec-head">
        <div>
          <div class="rec-title">★ 추천: {{ shownRec.airline_name }} {{ shownRec.flight_number }}
            <span v-if="!rec" class="badge gray">저장된 실행 결과</span>
          </div>
          <div class="rec-sub">
            {{ shownRec.dep_date }} {{ shownRec.dep_time }} 출발 · {{ shownRec.arr_date }} {{ shownRec.arr_time || '' }} 도착
            · 공장 ETA +{{ shownRec.factory_eta_hours }}h
          </div>
        </div>
        <div class="rec-price">
          <div class="rate">kg당 {{ won(shownRec.rate_per_kg) }}원</div>
          <div class="total">총 {{ won(shownRec.total_krw) }}원</div>
        </div>
      </div>
      <div class="rec-badges">
        <span class="badge green">표준가 대비 -{{ shownRec.saving_pct }}% ({{ won(shownRec.saving_krw) }}원 절감)</span>
        <span v-if="shownRec.offload_safe" class="badge green">OFFLOAD-SAFE (차기편 {{ shownRec.next_flight_arr }} 도착)</span>
        <span v-else class="badge amber">OFFLOAD RISK</span>
        <span v-if="shownRec.meets_desired" class="badge blue">희망도착일 충족</span>
        <span class="badge amber">컨펌 기한 {{ shownRec.confirm_by }}</span>
      </div>
      <p class="rationale">{{ shownRec.rationale }}</p>
      <button class="primary" :disabled="booking || selStatus === 'BOOKED'" @click="confirmBooking">
        {{ selStatus === 'BOOKED' ? '예약 확정됨 ✔' : '이 조건으로 예약 확정' }}
      </button>
    </section>
  </div>
</template>

<style scoped>
.wrap { max-width: 1280px; margin: 0 auto; }
.sub { color: var(--sub); font-weight: 400; font-size: 12px; }
.table-box { max-height: 280px; overflow: auto; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: #f8fafc; }
tbody tr.sel { background: var(--blue-soft); }
.item { max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.pad { padding: 16px; }
.detail { margin-top: 14px; }
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.detail-head h3 { margin: 0; }
.info-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px 16px; margin-bottom: 14px; }
.info { background: #f8fafc; border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; }
.info label { display: block; font-size: 11px; color: var(--sub); margin-bottom: 3px; }
.info b { font-size: 13px; }
.red { color: var(--red); }
.lines tbody tr { cursor: default; }
.lines tbody tr:hover { background: transparent; }
.cw-note { margin-top: 8px; }
.grid { display: grid; grid-template-columns: 5fr 7fr; gap: 16px; align-items: start; margin-top: 16px; }
.log { max-height: 480px; overflow: auto; background: #0f172a; border-radius: 8px; padding: 12px; }
.log-line { font-size: 12.5px; color: #cbd5e1; padding: 3px 0; line-height: 1.5; }
.log-line.email { color: #93c5fd; }
.log-line.quotes { color: #fcd34d; }
.log-line.nego { color: #a5b4fc; }
.log-line.recommendation { color: #6ee7b7; font-weight: 700; }
.log-line.error { color: #fca5a5; }
.log-icon { display: inline-block; width: 22px; }
tr.winner { background: var(--green-soft); }
.market { margin-top: 10px; font-size: 13px; color: var(--sub); }
.rec { margin-top: 16px; border: 2px solid var(--green); border-radius: 10px; padding: 16px; background: var(--green-soft); }
.rec-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.rec-title { font-size: 16px; font-weight: 800; color: var(--green); }
.rec-sub { font-size: 12.5px; color: var(--sub); margin-top: 4px; }
.rec-price { text-align: right; }
.rec-price .rate { font-size: 18px; font-weight: 800; }
.rec-price .total { font-size: 12.5px; color: var(--sub); }
.rec-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.rationale { font-size: 13px; line-height: 1.7; white-space: pre-wrap; background: #fff; border-radius: 8px; padding: 12px; margin: 0 0 12px; }
</style>
