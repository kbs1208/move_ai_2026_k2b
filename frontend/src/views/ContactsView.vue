<script setup>
import { onMounted, ref } from 'vue'
import { getJSON } from '../api.js'

const rows = ref([])
onMounted(async () => { rows.value = await getJSON('/api/contacts') })

const colors = ['#1d4ed8', '#059669', '#d97706', '#7c3aed', '#db2777', '#0891b2', '#dc2626']
const color = (code) => colors[(code.charCodeAt(0) + code.charCodeAt(1)) % colors.length]
</script>

<template>
  <div class="wrap">
    <h2>항공사 담당자 <span class="sub">예약/네고 컨택 포인트 및 AWB prefix</span></h2>
    <div class="panel pad">
      <table>
        <thead>
          <tr><th>항공사</th><th>코드</th><th>담당자</th><th>이메일</th><th>AWB Prefix</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in rows" :key="c.code">
            <td class="airline">
              <span class="avatar" :style="{ background: color(c.code) }">{{ c.airline[0] }}</span>
              <b>{{ c.airline }}</b>
            </td>
            <td><span class="badge blue">{{ c.code }}</span></td>
            <td>{{ c.name }}</td>
            <td class="mono">{{ c.email }}</td>
            <td><span class="badge gray mono">{{ c.awb_prefix }}-XXXXXXXX</span></td>
          </tr>
        </tbody>
      </table>
      <div class="note sub">AWB = prefix 3자리 + 시리얼 7자리 + 체크디짓 1자리 (총 11자리) — 예약 확정 시 자동 채번되어 항공사에 회신됩니다</div>
    </div>
  </div>
</template>

<style scoped>
.wrap { max-width: 960px; margin: 0 auto; }
.sub { color: var(--sub); font-weight: 400; font-size: 12px; }
.pad { padding: 16px; }
.mono { font-family: ui-monospace, monospace; font-size: 12.5px; }
.airline { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 30px; height: 30px; border-radius: 50%; color: #fff; font-weight: 700; font-size: 13px;
  display: inline-flex; align-items: center; justify-content: center; flex: none;
}
.note { margin-top: 10px; }
</style>
