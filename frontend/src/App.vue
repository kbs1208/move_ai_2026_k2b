<script setup>
import { ref } from 'vue'
import OrdersView from './views/OrdersView.vue'
import DashboardView from './views/DashboardView.vue'
import RatesView from './views/RatesView.vue'
import SchedulesView from './views/SchedulesView.vue'
import ContactsView from './views/ContactsView.vue'

const tab = ref('orders')
const menus = [
  { id: 'orders', label: '주문 · AI 에이전트', icon: '✈' },
  { id: 'rates', label: '가격 테이블', icon: '₩' },
  { id: 'sched', label: '스케줄 테이블', icon: '⏱' },
  { id: 'contacts', label: '항공사 담당자', icon: '☎' },
  { id: 'dash', label: '운영 대시보드', icon: '▦' },
]
</script>

<template>
  <aside class="sidebar">
    <div class="logo">
      <img src="/logo.png" alt="airnego — AIR CARGO NEGOTIATION AGENT" class="logo-img" />
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
    <RatesView v-else-if="tab === 'rates'" />
    <SchedulesView v-else-if="tab === 'sched'" />
    <ContactsView v-else-if="tab === 'contacts'" />
    <DashboardView v-else />
  </main>
</template>

<style scoped>
.sidebar {
  width: 220px; flex: none; background: #0f172a; color: #cbd5e1;
  display: flex; flex-direction: column; padding: 18px 12px;
}
.logo { padding: 2px 4px 16px; border-bottom: 1px solid #1e293b; }
.logo-img {
  display: block; width: 100%; max-width: 176px; margin: 0 auto;
  background: #fff; border-radius: 10px; padding: 8px 10px; box-sizing: border-box;
}
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
