<script setup>
import { ref } from 'vue'
import OrdersView from './views/OrdersView.vue'
import MailView from './views/MailView.vue'
import DashboardView from './views/DashboardView.vue'
import RatesView from './views/RatesView.vue'
import SchedulesView from './views/SchedulesView.vue'

const tab = ref('orders')
const menus = [
  { id: 'orders', label: '주문 · AI 에이전트', icon: '✈' },
  { id: 'mail', label: '메일함', icon: '✉' },
  { id: 'rates', label: '가격 테이블', icon: '₩' },
  { id: 'sched', label: '스케줄 테이블', icon: '⏱' },
  { id: 'dash', label: '운영 대시보드', icon: '▦' },
]
</script>

<template>
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-mark">A</div>
      <div>
        <div class="logo-title">Air Nego</div>
        <div class="logo-sub">AirCargo Nego Agent · ICN</div>
      </div>
    </div>
    <nav>
      <a v-for="m in menus" :key="m.id" :class="{ active: tab === m.id }" @click="tab = m.id">
        <span class="icon">{{ m.icon }}</span>{{ m.label }}
      </a>
    </nav>
    <div class="clock">DEMO CLOCK<br /><b>2026-08-08 (토)</b></div>
  </aside>
  <main class="content">
    <OrdersView v-if="tab === 'orders'" />
    <MailView v-else-if="tab === 'mail'" />
    <RatesView v-else-if="tab === 'rates'" />
    <SchedulesView v-else-if="tab === 'sched'" />
    <DashboardView v-else />
  </main>
</template>

<style scoped>
.sidebar {
  width: 220px; flex: none; background: #0f172a; color: #cbd5e1;
  display: flex; flex-direction: column; padding: 18px 12px;
}
.logo { display: flex; gap: 10px; align-items: center; padding: 4px 8px 18px; border-bottom: 1px solid #1e293b; }
.logo-mark {
  width: 34px; height: 34px; border-radius: 8px; background: var(--blue);
  color: #fff; font-weight: 800; font-size: 18px; display: flex; align-items: center; justify-content: center;
}
.logo-title { font-weight: 700; color: #f1f5f9; font-size: 14px; }
.logo-sub { font-size: 11px; color: #64748b; }
nav { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; flex: 1; }
nav a {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px;
  font-size: 13px; cursor: pointer; color: #94a3b8;
}
nav a:hover { background: #1e293b; }
nav a.active { background: #1d4ed8; color: #fff; font-weight: 600; }
.icon { width: 16px; text-align: center; }
.clock { font-size: 11px; color: #64748b; padding: 12px 8px; border-top: 1px solid #1e293b; line-height: 1.7; }
.clock b { color: #e2e8f0; font-size: 13px; }
.content { flex: 1; overflow: auto; padding: 20px 24px; }
</style>
