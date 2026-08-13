<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, won } from '../api.js'

const data = ref(null)
onMounted(async () => { data.value = await getJSON('/api/rates') })
</script>

<template>
  <div class="wrap" v-if="data">
    <h2>항공사 가격 테이블 <span class="sub">항공사가 제시한 표준 운임 (weight-break, KRW/kg)</span></h2>

    <div class="panel pad">
      <h3>운임 요율표 (Freight Rates)</h3>
      <table>
        <thead>
          <tr>
            <th>항공사</th><th>구간</th><th>유형</th><th>서비스</th>
            <th class="num">MIN</th><th class="num">N (&lt;45)</th><th class="num">45+</th>
            <th class="num">100+</th><th class="num">300+</th><th class="num">500+</th><th class="num">1000+</th>
            <th>적용기간</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in data.rates" :key="r.TARIFF_ID">
            <td><b>{{ r.CARRIER_NM }}</b> <span class="mono sub">{{ r.CARRIER_CD }}</span></td>
            <td>{{ r.DPRT_AIRPORT }} → {{ r.ARRV_AIRPORT }}</td>
            <td><span :class="['badge', r.FLIGHT_TYPE === 'CARGO' ? 'blue' : 'gray']">
              {{ r.FLIGHT_TYPE === 'CARGO' ? '화물기' : '여객기' }}</span></td>
            <td>{{ r.SERVICE_LEVEL }}</td>
            <td class="num">{{ won(r.MIN) }}</td>
            <td class="num">{{ won(r.N) }}</td>
            <td class="num">{{ won(r['45']) }}</td>
            <td class="num">{{ won(r['100']) }}</td>
            <td class="num">{{ won(r['300']) }}</td>
            <td class="num">{{ won(r['500']) }}</td>
            <td class="num"><b>{{ won(r['1000']) }}</b></td>
            <td class="sub">{{ r.EFFECTIVE_START_DATE }} ~ {{ r.EFFECTIVE_END_DATE }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel pad">
      <h3>할증료 (Surcharges, KRW/kg — 항공사별)</h3>
      <table style="max-width: 860px">
        <thead>
          <tr><th>항공사</th><th>도착 지역</th><th class="num">유류 할증</th><th class="num">보안 할증</th><th>적용기간</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in data.surcharges" :key="s.CARRIER_CD + s.ARRV_REGION">
            <td><b>{{ s.CARRIER_NM }}</b> <span class="mono sub">{{ s.CARRIER_CD }}</span></td>
            <td>{{ s.ARRV_REGION }}</td>
            <td class="num">{{ won(s.FUEL_SURCHARGE_KG) }}</td>
            <td class="num">{{ won(s.SEC_SURCHARGE_KG) }}</td>
            <td class="sub">{{ s.SUR_EFFECTIVE_START_DATE }} ~ {{ s.SUR_EFFECTIVE_END_DATE }}</td>
          </tr>
        </tbody>
      </table>
      <div class="note sub">all-in 단가 = weight-break 운임 + 해당 항공사 유류/보안 할증 (MIN 하한 적용)</div>
    </div>
  </div>
</template>

<style scoped>
.wrap { max-width: 1280px; margin: 0 auto; }
.sub { color: var(--sub); font-weight: 400; font-size: 12px; }
.pad { padding: 16px; margin-bottom: 16px; }
.mono { font-family: ui-monospace, monospace; }
.narrow { max-width: 640px; }
.note { margin-top: 10px; }
</style>
