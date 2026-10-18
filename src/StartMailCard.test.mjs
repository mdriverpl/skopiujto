import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./StartMailCard.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'start-mail-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function card(api, storage = new Map()) {
  const mounted = [], destroyed = [], listeners = new Map()
  let interval, cleared = false
  const surface = { visibilityState: 'visible', addEventListener(name, fn) { listeners.set(name, fn) }, removeEventListener(name) { listeners.delete(name) } }
  const events = []
  const context = { computed, ref, localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) }, onMounted(fn) { mounted.push(fn) }, onBeforeUnmount(fn) { destroyed.push(fn) },
    document: surface, window: surface, setInterval(fn) { interval = fn; return 1 }, clearInterval() { cleared = true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api }, { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, listeners, surface, mount() { mounted.forEach(fn => fn()) }, tick() { interval() }, destroy() { destroyed.forEach(fn => fn()); return cleared } }
}

test('start card loads only mailbox counters and retains them on a refresh failure', async () => {
  const calls = []
  let fail = false
  const item = card(async path => { calls.push(path); if (fail) throw new Error('Offline'); return { total: 12, unread: 4, urgent: 1 } })
  await item.state.refresh()
  assert.deepEqual(calls, ['/client-mail/summary?hours=24'])
  assert.equal(item.state.stats.value.unread, 4)
  fail = true
  await item.state.refresh()
  assert.equal(item.state.stats.value.unread, 4)
  assert.match(item.state.error.value, /odświeżyć/)
})

test('period buttons update statistics, persist choice and open inbox with the same range', async () => {
  const storage = new Map([['edokumenty-mail-range:inbox', '48']]), calls = []
  const item = card(async path => { calls.push(path); return { total: 20, unread: 12, today: 1, period: 8, period_unread: 5, period_clients: 3 } }, storage)
  await item.state.refresh()
  assert.equal(calls[0], '/client-mail/summary?hours=48')
  assert.equal(item.state.period.value.total, 8)
  assert.equal(item.state.period.value.clients, 3)
  await item.state.selectRange(168)
  assert.equal(calls[1], '/client-mail/summary?hours=168')
  assert.equal(storage.get('edokumenty-mail-range:inbox'), '168')
  assert.equal(item.state.rangeLabel.value, '7 dni')
  assert.equal(card(async () => ({}), storage).state.hours.value, 168)
  item.state.openMailbox()
  assert.equal(item.events[0][0], 'open')
})

test('refresh runs only while visible and stops when leaving Start', async () => {
  let calls = 0
  const item = card(async () => { calls++; return { total: 0, unread: 0, urgent: 0 } })
  item.mount()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls, 1)
  item.surface.visibilityState = 'hidden'; item.tick()
  assert.equal(calls, 1)
  item.surface.visibilityState = 'visible'; item.tick()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls, 2)
  assert.equal(item.destroy(), true)
  assert.equal(item.listeners.size, 0)
  await item.state.refresh()
  assert.equal(calls, 2)
})
