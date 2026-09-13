<script setup lang="ts">
import { computed, ref } from 'vue'
import { Command, Copy, Check } from 'lucide-vue-next'

const props = defineProps<{
  adwId: string
  status: string
  notAcceptedReason: string | null
}>()

interface Action {
  label: string
  command: string
}

const ACTIONS: Record<string, Action[]> = {
  running: [
    { label: 'watch the live tail', command: 'just tail {id}' },
    { label: 'inspect what is alive', command: 'just procs {id}' },
    { label: 'stop it', command: 'just kill {id}' },
  ],
  fail: [
    { label: 'inspect the phases', command: 'just phases {id}' },
    { label: 'read the events', command: 'just tail {id}' },
    { label: 'fix, then resume this run', command: 'just sdlc "..." --adw-id {id}' },
  ],
  not_accepted: [
    { label: 'inspect the phases', command: 'just phases {id}' },
    { label: 're-run and let it try again', command: 'just sdlc "..." --adw-id {id}' },
  ],
  success: [
    { label: 'document the work', command: 'just document "..."' },
    { label: 'review the run', command: 'just sessions' },
  ],
}

const actions = computed<Action[]>(() =>
  (ACTIONS[props.status] ?? ACTIONS.fail).map((action) => ({
    label: action.label,
    command: action.command.replace('{id}', props.adwId),
  })))

const copied = ref<string | null>(null)

async function copy(action: Action): Promise<void> {
  await navigator.clipboard.writeText(action.command)
  copied.value = action.command
  setTimeout(() => (copied.value = null), 1200)
}
</script>

<template>
  <div v-if="notAcceptedReason || actions.length" class="next-actions" data-testid="next-actions">
    <p v-if="notAcceptedReason" class="reason">
      <Command class="icon" :size="16" :stroke-width="2" />
      not accepted: {{ notAcceptedReason }}
    </p>
    <p class="heading">next actions</p>
    <ul class="actions">
      <li v-for="action in actions" :key="action.label">
        <span class="label">{{ action.label }}</span>
        <button
          class="command"
          :aria-label="`copy command: ${action.command}`"
          @click="copy(action)"
        >
          <code>{{ action.command }}</code>
          <Check v-if="copied === action.command" class="copied" :size="14" :stroke-width="2.5" />
          <Copy v-else class="copy-icon" :size="14" :stroke-width="2" />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.next-actions {
  margin: 0 24px 18px;
  padding: 14px 18px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--panel);
}

.reason {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--amber, #fbbf24);
  font-size: 15px;
}

.heading {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.actions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.actions li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.label {
  font-size: 14px;
  color: var(--text);
}

.command {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: transparent;
  color: var(--dim);
  cursor: pointer;
  font: inherit;
}

.command:hover {
  color: var(--text);
  border-color: var(--dim);
}

.command code {
  font-size: 13px;
}

.copied {
  color: var(--green);
}

@media (max-width: 640px) {
  .actions li {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>
