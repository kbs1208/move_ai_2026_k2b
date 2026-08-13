<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON } from '../api.js'

const rows = ref([])
const dest = ref('all')
onMounted(async () => { rows.value = await getJSON('/api/schedules') })

const dests = computed(() => [...new Set(rows.value.map((r) => r.dest_airport))].sort())
const shown = computed(() =>
  dest.value === 'all' ? rows.value : rows.value.filter((r) => r.dest_airport === dest.value)
)
const DAYS = ['월', '화', '수', '목', '금', '토', '일']
</script>

<template>
  <div class="wrap">
    <h2>항공사 스케줄 테이블
      <span class="sub">요일 패턴 × 유효기간 (ICN 출발)</span>
    </h2>
    <div class="filters">
      <a :class="{ on: dest === 'all' }" @click="dest = 'all'">전체 ({{ rows.length }})</a>
      <a v-for="d in dests" :key="d" :class="{ on: dest === d }" @click="dest = d">{{ d }}</a>
    </div>
    <div class="panel pad">
      <table>
        <thead>
          <tr>
            <th>편명</th><th>항공사</th><th>유형</th><th>구간</th><th>출발(KST)</th><th>도착(KST)</th>
            <th>운항 요일</th><th>유효기간</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in shown" :key="r.schedule_id">
            <td class="mono"><b>{{ r.flight_number }}</b></td>
            <td>{{ r.airline_name }}</td>
            <td><span :class="['badge', r.flight_type === 'CARGO' ? 'blue' : 'gray']">
              {{ r.flight_type === 'CARGO' ? '화물기' : '여객기' }}</span></td>
            <td>{{ r.origin_airport }} → {{ r.dest_airport }}</td>
            <td class="mono">{{ r.departure_time }}</td>
            <td class="mono">{{ r.arrival_time }}
              <span v-if="Number(r.date_differ) === 1" class="badge amber">+1일</span>
              <span v-else-if="Number(r.date_differ) === -1" class="badge amber">-1일</span>
            </td>
            <td>
              <span v-for="(on, i) in r.ops" :key="i" :class="['day', { on: on === 1 }]">{{ DAYS[i] }}</span>
            </td>
            <td class="sub">{{ r.start_date }} ~ {{ r.end_date }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.wrap { max-width: 1280px; margin: 0 auto; }
.sub { color: var(--sub); font-weight: 400; font-size: 12px; }
.pad { padding: 16px; }
.mono { font-family: ui-monospace, monospace; font-size: 12.5px; }
.filters { display: flex; gap: 8px; margin: 0 0 12px; font-size: 13px; }
.filters a { cursor: pointer; color: var(--sub); padding: 4px 12px; border-radius: 999px; background: #fff; border: 1px solid var(--line); }
.filters a.on { background: var(--blue); color: #fff; border-color: var(--blue); font-weight: 700; }
.day {
  display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center;
  border-radius: 4px; font-size: 11px; margin-right: 2px; background: #f1f5f9; color: #cbd5e1;
}
.day.on { background: var(--blue-soft); color: var(--blue); font-weight: 700; }
</style>
