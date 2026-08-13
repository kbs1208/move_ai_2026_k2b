<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { getJSON, md, postJSON, won } from '../api.js'
import { runs, dataVersion, startAgent } from '../agentRuns.js'

const orders = ref([])
const selected = ref(null)
const booking = ref(false)
const logBox = ref(null)
const mailTab = ref(null)        // 네고 메일 내역: 선택된 항공사 코드
const savedThreads = ref([])     // 저장된 추천용 메일 스레드 (서버에서 로드)

async function loadOrders(keepSel = false) {
  const no = selected.value?.order_no
  orders.value = await getJSON('/api/orders')
  if (keepSel && no) selected.value = orders.value.find((o) => o.order_no === no) || null
}
onMounted(loadOrders)
// 다른 접속자의 실행/예약/취소까지 실시간 반영
watch(dataVersion, () => loadOrders(true))

// 선택 주문의 실행 슬롯 (전역 스토어 — 모든 접속자 공통 상태)
const run = computed(() => runs[selected.value?.order_no] || null)
// 화면에 보여줄 추천: 이번 실행 결과 우선, 없으면 DB에 저장된 추천
const shownRec = computed(() => run.value?.rec || selected.value?.recommendation || null)

// 타임라인 자동 스크롤
watch(() => run.value?.events.length, () => {
  nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
})

function select(o) {
  selected.value = o
  mailTab.value = null
  savedThreads.value = []
  // 라이브 실행 이력이 없는 주문의 저장된 추천이면 서버에서 메일 스레드 복원
  if (!runs[o.order_no] && o.recommendation) refreshThreads(o.order_no)
}

// 네고 메일 내역 (라이브 스레드 우선, 없으면 저장본)
const negoThreads = computed(() => {
  const live = run.value ? Object.values(run.value.threads) : []
  return live.length ? live : savedThreads.value
})
watch(negoThreads, (ts) => {
  if (ts.length && !ts.find((t) => t.carrier === mailTab.value)) mailTab.value = ts[0].carrier
})
const mailThread = computed(() => negoThreads.value.find((t) => t.carrier === mailTab.value))

// 메일 아코디언: 기본은 최신 메일만 펼침, 새 메일 도착 시 최신으로 갱신
const expanded = ref(new Set())
watch(() => [mailTab.value, mailThread.value?.messages.length], () => {
  const n = mailThread.value?.messages.length || 0
  expanded.value = new Set(n ? [n - 1] : [])
})
function toggleMsg(i) {
  const s = new Set(expanded.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expanded.value = s
}
function expandAll() {
  expanded.value = new Set((mailThread.value?.messages || []).map((_, i) => i))
}
function collapseAll() {
  expanded.value = new Set()
}
const preview = (body) => body.split('\n').find((l) => l.trim()) || ''

async function start() {
  const no = selected.value?.order_no
  if (!no || runs[no]?.running) return
  savedThreads.value = []
  await startAgent(no) // 서버 백그라운드 실행 — 진행 상황은 전역 SSE로 모든 접속자에게 수신
}

async function refreshThreads(no) {
  // 서버에 저장된 최신 스레드로 갱신 (AWB 회신/클로징 메일 반영)
  const all = await getJSON('/api/emails')
  const mine = all.filter((t) => t.order_no === no)
  const byCarrier = {}
  for (const t of mine.reverse()) byCarrier[t.carrier] = t
  if (runs[no]) {
    for (const [c, t] of Object.entries(byCarrier)) if (runs[no].threads[c]) runs[no].threads[c] = t
  } else {
    savedThreads.value = Object.values(byCarrier)
  }
}

async function confirmBooking() {
  booking.value = true
  await postJSON('/api/bookings', shownRec.value)
  await loadOrders(true)
  await refreshThreads(selected.value.order_no)
  booking.value = false
}

const statusColor = { PENDING: 'blue', AWAITING: 'amber', BOOKED: 'green' }
const icons = {
  start: '▶', candidates: '🔍', history: '📊', progress: '…', email: '✉',
  quotes: '💰', nego: '🤝', recommendation: '★', done: '✔', error: '✖',
}
const fmt = (n, d = 2) => (n == null ? '-' : Number(n).toLocaleString('ko-KR', { maximumFractionDigits: d }))
const initials = (name) => name.trim()[0].toUpperCase()
</script>

<template>
  <div class="wrap">
    <h2>KD 주문 정보 <span class="sub">주문을 선택하고 AI 에이전트를 실행하세요 (여러 주문 동시 실행 가능)</span></h2>
    <div class="panel table-box">
      <table>
        <thead>
          <tr>
            <th>주문번호</th><th>구간</th><th>품목</th><th class="num">CW (kg)</th><th class="num">CBM</th>
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
            <td class="num">{{ fmt(o.size_cbm) }}</td>
            <td><span v-if="o.is_dg" class="badge amber">DG</span><span v-else class="badge gray">-</span></td>
            <td>{{ o.cargo_ready_date }}</td>
            <td>{{ o.desired_arr_date }}</td>
            <td><b>{{ o.deadline_date }}</b></td>
            <td>
              <span v-if="runs[o.order_no]?.running" :key="runs[o.order_no].rfqReplied"
                    class="badge running">✉ {{ runs[o.order_no].rfqReplied }}/{{ runs[o.order_no].rfqTotal || '-' }}</span>
              <span v-else :class="['badge', statusColor[o.status] || 'gray']">{{ o.status }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 주문 상세 -->
    <section v-if="selected" class="panel pad detail">
      <div class="detail-head">
        <h3>주문 상세 <span class="mono sub">{{ selected.order_no }}</span></h3>
        <!-- BOOKED = 종착 상태: 재실행/취소 불가 -->
        <button v-if="selected.status === 'BOOKED'" class="booked" disabled>예약 확정 ✔</button>
        <button v-else class="primary"
                :disabled="run?.running || selected.status === 'AWAITING'" @click="start">
          {{ run?.running ? 'AI 에이전트 실행 중...'
             : selected.status === 'AWAITING' ? 'AI 에이전트 실행 (추천 확정 대기)'
             : 'AI 에이전트 실행' }}
        </button>
      </div>
      <div class="info-grid">
        <div class="info"><label>구간</label><b>{{ selected.origin }} → {{ selected.dest }}</b></div>
        <div class="info"><label>품목</label><b>{{ selected.item_name }}</b></div>
        <div class="info"><label>위험물(DG)</label>
          <b><span v-if="selected.is_dg" class="badge amber">DG — 화물기만 가능</span><span v-else>일반 화물</span></b></div>
        <div class="info"><label>상태</label>
          <b><span :class="['badge', statusColor[selected.status] || 'gray']">{{ selected.status }}</span></b></div>
        <div class="info"><label>화물 준비일</label><b>{{ selected.cargo_ready_date }}</b></div>
        <div class="info"><label>희망 도착일</label><b>{{ selected.desired_arr_date }}</b></div>
        <div class="info"><label>데드라인</label><b class="red">{{ selected.deadline_date }}</b></div>
        <div class="info"><label>총 수량</label><b>{{ selected.pieces }} pcs</b></div>
        <div class="info"><label>실중량 (GW)</label><b>{{ fmt(selected.gross_weight_kg) }} kg</b></div>
        <div class="info"><label>청구중량 (CW)</label><b>{{ fmt(selected.chargeable_weight_kg) }} kg</b></div>
        <div class="info"><label>총 부피 (CBM)</label><b>{{ fmt(selected.size_cbm) }} m³</b></div>
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
      <div class="cw-note sub">CW = max(실중량, 가로×세로×높이/6,000×수량) · CBM = 가로×세로×높이/1,000,000×수량 — 라인 합산</div>
    </section>

    <div v-if="run?.events.length" class="grid">
      <section class="panel pad">
        <h3>에이전트 타임라인</h3>
        <div class="log" ref="logBox">
          <div v-for="(ev, i) in run.events" :key="i" :class="['log-line', ev.type]">
            <span class="log-icon">{{ icons[ev.type] || '·' }}</span>{{ ev.message }}
          </div>
        </div>
      </section>

      <section class="panel pad">
        <h3>항공사별 견적 · 네고 현황 <span v-if="run.candCount" class="sub">(운항 후보 {{ run.candCount }}편)</span></h3>
        <table>
          <thead>
            <tr><th>항공사 / 편</th><th>출발일</th><th>도착</th><th class="num">표준가</th><th class="num">첫 견적</th>
                <th class="num">최종가</th><th>안전성</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in run.picks" :key="p.carrier"
                :class="{ winner: run.rec && run.rec.carrier === p.carrier }">
              <td><b>{{ p.airline_name }}</b> <span class="mono sub">{{ p.flight_number }}</span>
                  <span :class="['badge', p.flight_type === 'CARGO' ? 'blue' : 'gray']">{{ p.flight_type === 'CARGO' ? '화물기' : '여객기' }}</span></td>
              <td>{{ p.dep_date }}</td>
              <td>{{ p.arr_date }} <span class="sub">{{ p.arr_time }}</span></td>
              <td class="num">{{ won(run.carrierState[p.carrier]?.std) }}</td>
              <td class="num">{{ won(run.carrierState[p.carrier]?.quote) }}</td>
              <td class="num"><b>{{ won(run.carrierState[p.carrier]?.last) }}</b>
                <span v-if="run.carrierState[p.carrier]?.decision === 'accept'" class="badge green">수락</span></td>
              <td>
                <span v-if="p.offload_safe" class="badge green">SAFE</span>
                <span v-else class="badge amber">RISK</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="run.market" class="market">
          시장 range: <b>kg당 {{ won(run.market.low) }} ~ {{ won(run.market.high) }}원</b> ({{ run.market.n }}개사 견적)
        </div>
      </section>
    </div>

    <!-- 추천 (이번 실행 or 저장된 결과) -->
    <section v-if="shownRec" class="rec">
      <div class="rec-head">
        <div>
          <div class="rec-title">★ 추천: {{ shownRec.airline_name }} {{ shownRec.flight_number }}
            <span v-if="!run?.rec" class="badge gray">저장된 실행 결과</span>
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
        <span v-if="selected?.awb" class="badge awb">AWB {{ selected.awb }}</span>
      </div>
      <div class="rationale" v-html="md(shownRec.rationale)"></div>
      <button class="primary" :disabled="booking || selected?.status === 'BOOKED'" @click="confirmBooking">
        {{ selected?.status === 'BOOKED' ? '예약 확정됨 ✔' : '이 조건으로 예약 확정' }}
      </button>

      <!-- 네고 메일 내역 (항공사별 탭 + 메일 아코디언 + 스크롤) -->
      <div v-if="negoThreads.length" class="mails">
        <div class="mails-head">
          <h3>네고 메일 내역 <span class="sub">이 주문을 위해 주고받은 메일 — 클릭하면 펼쳐집니다</span></h3>
          <div class="mail-actions">
            <a @click="expandAll">모두 펼치기</a><a @click="collapseAll">모두 접기</a>
          </div>
        </div>
        <div class="mail-tabs">
          <a v-for="t in negoThreads" :key="t.carrier"
             :class="{ on: mailTab === t.carrier, win: shownRec.carrier === t.carrier }"
             @click="mailTab = t.carrier">
            {{ t.airline }} <span class="cnt">{{ t.messages.length }}</span>
            <span v-if="shownRec.carrier === t.carrier">★</span>
          </a>
        </div>
        <div v-if="mailThread" class="mail-msgs">
          <div v-for="(m, i) in mailThread.messages" :key="i"
               class="msg" :class="[m.direction, { open: expanded.has(i) }]">
            <div class="msg-head" @click="toggleMsg(i)">
              <div class="avatar" :class="m.direction">{{ initials(m.from_name) }}</div>
              <div class="msg-meta">
                <div><b>{{ m.from_name }}</b> <span class="addr">&lt;{{ m.from }}&gt;</span>
                  <span class="to">· {{ m.ts }}</span></div>
                <div v-if="!expanded.has(i)" class="prev">{{ preview(m.body) }}</div>
                <div v-else class="to">to {{ m.to }}</div>
              </div>
              <span :class="['badge', m.direction === 'out' ? 'gray' : 'blue']">
                {{ m.direction === 'out' ? '발송' : '수신' }}</span>
              <span class="chev">{{ expanded.has(i) ? '▾' : '▸' }}</span>
            </div>
            <div v-if="expanded.has(i)" class="body">{{ m.body }}</div>
          </div>
        </div>
      </div>
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
.item { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.pad { padding: 16px; }
.detail { margin-top: 14px; }
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.detail-head h3 { margin: 0; }
button.booked {
  background: var(--green); color: #fff; border: 0; border-radius: 8px;
  padding: 10px 18px; font-size: 14px; font-weight: 700; cursor: default; opacity: 1;
}
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

/* 실행 중 n/m 배지: 회신 수신마다 flash + 상시 pulse */
.badge.running {
  background: #ede9fe; color: #7c3aed; font-family: ui-monospace, monospace;
  animation: flash 0.7s ease, pulse 1.6s ease 0.7s infinite;
}
.badge.awb { background: #0f172a; color: #fff; font-family: ui-monospace, monospace; }
@keyframes flash {
  0% { background: #7c3aed; color: #fff; transform: scale(1.25); }
  100% { background: #ede9fe; color: #7c3aed; transform: scale(1); }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.rec { margin-top: 16px; border: 2px solid var(--green); border-radius: 10px; padding: 16px; background: var(--green-soft); }
.rec-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.rec-title { font-size: 16px; font-weight: 800; color: var(--green); }
.rec-sub { font-size: 12.5px; color: var(--sub); margin-top: 4px; }
.rec-price { text-align: right; }
.rec-price .rate { font-size: 18px; font-weight: 800; }
.rec-price .total { font-size: 12.5px; color: var(--sub); }
.rec-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.rationale { font-size: 13px; line-height: 1.7; background: #fff; border-radius: 8px; padding: 12px 14px; margin: 0 0 12px; }
.rationale :deep(p) { margin: 2px 0; }
.rationale :deep(h4) { margin: 10px 0 4px; font-size: 13.5px; color: var(--green); }
.rationale :deep(.md-li) { margin: 3px 0 3px 8px; }
.rationale :deep(.md-gap) { height: 6px; }
.rationale :deep(code) { background: #f1f5f9; border-radius: 4px; padding: 1px 5px; font-size: 12px; }

/* 네고 메일 내역 */
.mails { margin-top: 16px; border-top: 1px dashed var(--green); padding-top: 14px; }
.mails-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.mails-head h3 { margin: 0; }
.mail-actions { display: flex; gap: 6px; font-size: 12px; }
.mail-actions a {
  cursor: pointer; color: var(--sub); padding: 3px 10px; border-radius: 6px;
  background: #fff; border: 1px solid var(--line);
}
.mail-actions a:hover { color: var(--blue); border-color: var(--blue); }
.mail-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.mail-tabs a {
  cursor: pointer; font-size: 12.5px; padding: 5px 12px; border-radius: 999px;
  background: #fff; border: 1px solid var(--line); color: var(--sub);
}
.mail-tabs a.on { background: var(--blue); border-color: var(--blue); color: #fff; font-weight: 700; }
.mail-tabs a.win:not(.on) { border-color: var(--green); color: var(--green); }
.mail-tabs .cnt { font-size: 11px; opacity: 0.75; }
.mail-msgs { display: flex; flex-direction: column; gap: 8px; max-height: 480px; overflow: auto; padding-right: 4px; }
.msg { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: #fff; flex: none; }
.msg.out { border-left: 3px solid #334155; }
.msg.in { border-left: 3px solid var(--blue); }
.msg.open { box-shadow: 0 1px 6px rgba(15, 23, 42, 0.08); }
.msg-head { display: flex; gap: 10px; align-items: center; padding: 9px 12px; background: #f8fafc; font-size: 12.5px; cursor: pointer; user-select: none; }
.msg-head:hover { background: #f1f5f9; }
.msg-head .badge { margin-left: auto; flex: none; }
.msg-meta { min-width: 0; }
.prev { color: var(--sub); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 560px; }
.chev { color: var(--sub); font-size: 12px; flex: none; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; color: #fff; font-weight: 700; font-size: 12px;
  display: flex; align-items: center; justify-content: center; flex: none;
}
.avatar.out { background: #334155; }
.avatar.in { background: var(--blue); }
.addr { color: var(--sub); font-size: 11.5px; }
.to { color: var(--sub); font-size: 11px; }
.body { padding: 12px 14px; font-size: 13px; line-height: 1.75; white-space: pre-wrap; }
</style>
