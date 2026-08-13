<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON } from '../api.js'

const threads = ref([])
const current = ref(null)
const filter = ref('all')

async function load() {
  threads.value = await getJSON('/api/emails')
  if (!current.value && threads.value.length) current.value = threads.value[0]
}
onMounted(load)

const shown = computed(() =>
  filter.value === 'live' ? threads.value.filter((t) => t.live) : threads.value
)

const initials = (name) => name.trim()[0].toUpperCase()
const preview = (t) => t.messages[t.messages.length - 1]?.body.split('\n')[0] || ''
const colors = ['#1d4ed8', '#059669', '#d97706', '#7c3aed', '#db2777', '#0891b2', '#dc2626']
const color = (code) => colors[(code.charCodeAt(0) + code.charCodeAt(1)) % colors.length]
</script>

<template>
  <div class="mail">
    <aside class="list panel">
      <div class="list-head">
        <h2>메일함</h2>
        <div class="filters">
          <a :class="{ on: filter === 'all' }" @click="filter = 'all'">전체</a>
          <a :class="{ on: filter === 'live' }" @click="filter = 'live'">오늘 네고</a>
          <a class="refresh" @click="load">↻</a>
        </div>
      </div>
      <div class="items">
        <div v-for="t in shown" :key="t.thread_id" class="item"
             :class="{ sel: current?.thread_id === t.thread_id }" @click="current = t">
          <div class="avatar" :style="{ background: color(t.carrier) }">{{ initials(t.airline) }}</div>
          <div class="meta">
            <div class="row1">
              <span class="from">{{ t.airline }}</span>
              <span class="ts">{{ t.messages[t.messages.length - 1]?.ts.slice(5) }}</span>
            </div>
            <div class="subj">{{ t.subject }} <span v-if="t.live" class="badge blue">LIVE</span></div>
            <div class="prev">{{ preview(t) }}</div>
          </div>
        </div>
      </div>
    </aside>

    <section class="thread panel" v-if="current">
      <div class="thread-head">
        <h2>{{ current.subject }}</h2>
        <div class="sub">
          {{ current.airline }} · {{ current.contact.name }} &lt;{{ current.contact.email }}&gt;
          · 주문 {{ current.order_no }}
        </div>
      </div>
      <div class="msgs">
        <div v-for="(m, i) in current.messages" :key="i" class="msg" :class="m.direction">
          <div class="msg-head">
            <div class="avatar sm"
                 :style="{ background: m.direction === 'out' ? '#334155' : color(current.carrier) }">
              {{ initials(m.from_name) }}
            </div>
            <div>
              <b>{{ m.from_name }}</b> <span class="addr">&lt;{{ m.from }}&gt;</span>
              <div class="to">to {{ m.to }} · {{ m.ts }}</div>
            </div>
            <span v-if="m.direction === 'out'" class="badge gray">발송됨 (시뮬레이션)</span>
          </div>
          <div class="body">{{ m.body }}</div>
        </div>
      </div>
    </section>
    <section v-else class="thread panel empty">스레드를 선택하세요</section>
  </div>
</template>

<style scoped>
.mail { display: grid; grid-template-columns: 380px 1fr; gap: 16px; height: calc(100vh - 40px); max-width: 1400px; margin: 0 auto; }
.list { display: flex; flex-direction: column; overflow: hidden; }
.list-head { padding: 14px 16px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }
.list-head h2 { margin: 0; }
.filters { display: flex; gap: 8px; font-size: 12px; }
.filters a { cursor: pointer; color: var(--sub); padding: 3px 8px; border-radius: 6px; }
.filters a.on { background: var(--blue-soft); color: var(--blue); font-weight: 700; }
.items { overflow: auto; flex: 1; }
.item { display: flex; gap: 10px; padding: 11px 14px; border-bottom: 1px solid #f1f5f9; cursor: pointer; }
.item:hover { background: #f8fafc; }
.item.sel { background: var(--blue-soft); }
.avatar {
  width: 36px; height: 36px; border-radius: 50%; color: #fff; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex: none; font-size: 15px;
}
.avatar.sm { width: 30px; height: 30px; font-size: 13px; }
.meta { min-width: 0; flex: 1; }
.row1 { display: flex; justify-content: space-between; }
.from { font-weight: 700; font-size: 13px; }
.ts { font-size: 11px; color: var(--sub); }
.subj { font-size: 12.5px; margin: 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prev { font-size: 12px; color: var(--sub); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.thread { overflow: auto; }
.thread-head { padding: 16px 20px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: #fff; z-index: 1; }
.thread-head h2 { margin: 0 0 4px; }
.sub { font-size: 12px; color: var(--sub); }
.msgs { padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }
.msg { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.msg.out { border-left: 3px solid #334155; }
.msg.in { border-left: 3px solid var(--blue); }
.msg-head { display: flex; gap: 10px; align-items: center; padding: 10px 14px; background: #f8fafc; font-size: 13px; }
.msg-head .badge { margin-left: auto; }
.addr { color: var(--sub); font-size: 12px; }
.to { color: var(--sub); font-size: 11px; }
.body { padding: 14px 16px; font-size: 13.5px; line-height: 1.8; white-space: pre-wrap; }
.empty { display: flex; align-items: center; justify-content: center; color: var(--sub); }
</style>
