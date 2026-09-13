<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { SessionSummary } from '../lib/types'
import { fetchSessions } from '../lib/api'
import { ts } from '../lib/format'
import SessionCard from './SessionCard.vue'

const sessions = shallowRef<SessionSummary[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const nowMs = ref(Date.now())

let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

async function tick() {
  if (inflight) return
  inflight = true
  try {
    sessions.value = await fetchSessions()
    nowMs.value = Date.now()
    apiError.value = null
    loaded.value = true
  } catch (err) {
    apiError.value = err instanceof Error ? err.message : String(err)
  } finally {
    inflight = false
  }
}

onMounted(() => {
  void tick()
  timer = setInterval(() => void tick(), 500)
})

onUnmounted(() => clearInterval(timer))

/** Optimistic removal; an empty id means the write failed, so re-sync instead. */
function onArchived(adwId: string) {
  if (!adwId) {
    void tick()
    return
  }
  sessions.value = sessions.value.filter((s) => s.adw_id !== adwId)
}

const FILTERS = ['all', 'running', 'success', 'fail'] as const

const activeFilter = ref<(typeof FILTERS)[number]>('all')

/** Sessions that failed with every phase green are 'not accepted' runs. */
function displayStatus(s: SessionSummary): string {
  if (s.status !== 'fail') return s.status ?? 'fail'
  const phases = s.phases ?? []
  if (phases.length > 0 && phases.every((p) => p.status === 'success')) {
    return 'not_accepted'
  }
  return 'fail'
}

const ordered = computed(() =>
  sessions.value
    .filter((s) => activeFilter.value === 'all' || displayStatus(s) === activeFilter.value)
    .toSorted((a, b) => (ts(b.started_at) || 0) - (ts(a.started_at) || 0)),
)
</script>

<template>
  <div class="sessions">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div class="filter" role="group" aria-label="filter runs by status">
      <button
        v-for="f in FILTERS"
        :key="f"
        class="filter-chip"
        :class="{ active: activeFilter === f }"
        :aria-pressed="activeFilter === f"
        @click="activeFilter = f"
      >
        {{ f }}
      </button>
    </div>

    <div v-if="ordered.length" class="list-head dim">{{ ordered.length }} runs</div>

    <div v-if="ordered.length" class="cards">
      <SessionCard
        v-for="s in ordered"
        :key="s.adw_id"
        :session="s"
        :now-ms="nowMs"
        @archived="onArchived"
      />
    </div>
    <div v-else-if="loaded" class="empty-state">no sessions yet — run an ADW to see it here</div>
    <div v-else-if="!apiError" class="empty-state">loading sessions…</div>
  </div>
</template>

<style scoped>
.sessions {
  display: flex;
  flex-direction: column;
}

.list-head {
  padding: 16px 24px 0;
  font-size: 16px;
}

.cards {
  /* Uniform grid: every card the same width and (fixed in SessionCard) height,
     independent of content. At phone width the grid collapses to one column. */
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
  gap: 18px;
  padding: 16px 24px 28px;
}

.filter {
  display: flex;
  gap: 8px;
  padding: 14px 24px 0;
}

.filter-chip {
  padding: 4px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--dim);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.filter-chip.active {
  color: var(--text);
  border-color: var(--dim);
}

.filter-chip:focus-visible {
  outline: 2px solid var(--dim);
  outline-offset: 2px;
}

@media (max-width: 640px) {
  .cards {
    grid-template-columns: 1fr;
    padding: 12px 16px 24px;
  }

  .filter {
    padding: 12px 16px 0;
  }
}





</style>
