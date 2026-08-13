<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, won } from '../api.js'

const data = ref(null)
onMounted(async () => { data.value = await getJSON('/api/dashboard') })

const carrierBars = computed(() => {
  if (!data.value) return []
  const entries = Object.entries(data.value.by_carrier).sort((a, b) => b[1].saving - a[1].saving)
  const max = Math.max(...entries.map(([, v]) => v.saving), 1)
  return entries.map(([name, v]) => ({ name, ...v, pct: (v.saving / max) * 100 }))
})
const destBars = computed(() => {
  if (!data.value) return []
  const entries = Object.entries(data.value.by_dest).sort((a, b) => b[1].saving - a[1].saving)
  const max = Math.max(...entries.map(([, v]) => v.saving), 1)
  return entries.map(([name, v]) => ({ name, ...v, pct: (v.saving / max) * 100 }))
})
</script>

<template>
  <div class="wrap" v-if="data">
    <h2>운영 대시보드 <span class="sub">표준가 대비 AI 네고 절감 실적 (최근 1개월 + 오늘)</span></h2>

    <div class="cards">
      <div class="panel card">
        <div class="label">누적 절감액</div>
        <div class="value green">{{ won(data.total_saving_krw) }}원</div>
      </div>
      <div class="panel card">
        <div class="label">평균 할인율 (표준가 대비)</div>
        <div class="value">{{ data.avg_discount_pct }}%</div>
      </div>
      <div class="panel card">
        <div class="label">네고 성사 건수</div>
        <div class="value">{{ data.deal_count }}건</div>
      </div>
    </div>

    <div class="grid2">
      <div class="panel pad">
        <h3>항공사별 절감액</h3>
        <div v-for="b in carrierBars" :key="b.name" class="bar-row">
          <div class="bar-label">{{ b.name }} <span class="sub">({{ b.count }}건)</span></div>
          <div class="bar-track"><div class="bar" :style="{ width: b.pct + '%' }"></div></div>
          <div class="bar-val num">{{ won(b.saving) }}원</div>
        </div>
      </div>
      <div class="panel pad">
        <h3>구간별 절감액</h3>
        <div v-for="b in destBars" :key="b.name" class="bar-row">
          <div class="bar-label">ICN → {{ b.name }} <span class="sub">({{ b.count }}건)</span></div>
          <div class="bar-track"><div class="bar dest" :style="{ width: b.pct + '%' }"></div></div>
          <div class="bar-val num">{{ won(b.saving) }}원</div>
        </div>
      </div>
    </div>

    <div class="panel pad">
      <h3>건별 네고 내역</h3>
      <table>
        <thead>
          <tr>
            <th>합의일</th><th>항공사</th><th>편명</th><th>구간</th><th>출발일</th>
            <th class="num">CW (kg)</th><th class="num">표준가/kg</th><th class="num">합의가/kg</th>
            <th class="num">절감액</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in data.rows" :key="i">
            <td>{{ r.date }}</td>
            <td>{{ r.airline }}</td>
            <td class="mono">{{ r.flight }}</td>
            <td>ICN→{{ r.dest }}</td>
            <td>{{ r.dep_date }}</td>
            <td class="num">{{ won(r.cw) }}</td>
            <td class="num">{{ won(r.std_rate) }}</td>
            <td class="num"><b>{{ won(r.final_rate) }}</b></td>
            <td class="num green"><b>-{{ won(r.saving_krw) }}</b></td>
            <td><span v-if="r.source === 'session'" class="badge blue">오늘 AI</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.wrap { max-width: 1280px; margin: 0 auto; }
.sub { color: var(--sub); font-weight: 400; font-size: 12px; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; }
.card { padding: 18px 20px; }
.label { font-size: 12px; color: var(--sub); margin-bottom: 8px; }
.value { font-size: 26px; font-weight: 800; }
.value.green, .green { color: var(--green); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.pad { padding: 16px; margin-bottom: 16px; }
.bar-row { display: grid; grid-template-columns: 170px 1fr 110px; gap: 10px; align-items: center; padding: 5px 0; font-size: 13px; }
.bar-track { background: #f1f5f9; border-radius: 4px; height: 14px; }
.bar { background: var(--blue); height: 100%; border-radius: 4px; }
.bar.dest { background: var(--green); }
.bar-val { text-align: right; font-size: 12.5px; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
</style>
