import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch, reactive, nextTick } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./MailAnalysis.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'analysis-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function page(api, overrides = {}) {
  const events = [], mounted = []
  const context = { computed, ref, watch, MailDayMessages: {}, onMounted(callback) { mounted.push(callback) } }
  runInNewContext(compiled, context)
  const state = context.component.setup(reactive({ api, ...overrides }), { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, mount: async () => { for (const callback of mounted) await callback() } }
}
const base = { sender_name: 'Jan', sender_email: 'jan@example.com', subject: 'Oferta', folder: 'inbox', direction: 'received', spam: false, unread: 1, created_at: '2026-10-16T08:30:00Z' }
const report = { stats: { total: 4, received: 3, sent: 1, urgent: 1, reply: 0, payment: 1, clients: 1, unread: 3, spam: 1, categories: { correspondence: 1, invoice: 1, spam: 1 } }, messages: [
  { ...base, id: 'urgent', label: 'urgent', category: 'correspondence', company: { id: 'a', name: 'Firma Alfa' } },
  { ...base, id: 'invoice', subject: 'Faktura 123', label: 'payment', category: 'invoice', folder: 'archive' },
  { ...base, id: 'spam', label: 'urgent', category: 'spam', spam: true },
  { ...base, id: 'sent', label: 'urgent', direction: 'sent', category: 'correspondence', folder: 'sent', unread: 0 }
], companies: [{ id: 'a', name: 'Firma Alfa', count: 1 }], generated_at: '2026-10-16T12:00:00Z', analysis: { recommendations: [] } }

test('standalone page loads only the local daily report and retains its selected date', async () => {
  const calls = []
  const { state, mount, events } = page(async (path, method, body) => { calls.push({ path, method, body }); return report }, { initialDay: '2026-10-16' })
  await mount()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].path, '/client-mail/day-report')
  assert.equal(calls[0].method, 'POST')
  assert.deepEqual(Object.keys(calls[0].body), ['day'])
  assert.equal(calls[0].body.day, '2026-10-16')
  assert.deepEqual(events[0], ['day-change', '2026-10-16'])
  assert.equal(state.loading.value, false)
})

test('action counts exclude spam and outgoing mail; categories account for all incoming mail', async () => {
  const { state, mount } = page(async () => report)
  await mount()
  assert.deepEqual(Array.from(state.actionable.value, item => item.id), ['urgent', 'invoice'])
  assert.equal(state.groups.value.find(group => group.id === 'urgent').items.length, 1)
  assert.equal(state.categoryRows.value.reduce((sum, item) => sum + item.count, 0), 3)
  assert.equal(state.percent(1), 33)
  assert.match(state.donut.value, /conic-gradient/)
  assert.equal(state.hours.value[10], 3)
  assert.equal(state.hours.value.reduce((a, b) => a + b, 0), 3)
  assert.equal(state.peak.value, '10:00')
})

test('cards and categories filter the searchable message list and emit the chosen message', async () => {
  const { state, mount, events } = page(async () => report)
  await mount()
  state.chooseGroup('category:invoice')
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['invoice'])
  state.search.value = '  FAKTURA 123 '
  assert.equal(state.filtered.value.length, 1)
  state.search.value = 'missing'
  assert.equal(state.filtered.value.length, 0)
  state.search.value = ''
  state.limit.value = 40
  state.chooseGroup('clients')
  await nextTick()
  assert.equal(state.limit.value, 12)
  assert.equal(state.filtered.value.length, 1)
  state.openMessage('invoice')
  assert.equal(events.at(-1)[0], 'open-message')
  assert.equal(events.at(-1)[1].folder, 'archive')
  assert.equal(events.at(-1)[1].id, 'invoice')
})

test('date navigation crosses month boundaries correctly and failures allow retry', async () => {
  let fail = true
  const { state } = page(async () => { if (fail) throw new Error('Brak połączenia'); return report }, { initialDay: '2026-03-31' })
  await state.moveDay(1)
  assert.equal(state.day.value, '2026-04-01')
  assert.match(state.error.value, /Brak połączenia/)
  assert.equal(state.loading.value, false)
  fail = false
  await state.loadReport()
  assert.equal(state.error.value, '')
  assert.equal(state.report.value.stats.total, 4)
})

test('empty day has neutral charts and zero percentages without invented activity', async () => {
  const { state, mount } = page(async () => ({ stats: { total: 0, received: 0, categories: {} }, messages: [], companies: [] }))
  await mount()
  assert.equal(state.percent(1), 0)
  assert.equal(state.donut.value, 'var(--border)')
  assert.equal(state.categoryRows.value.length, 0)
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.peak.value, '—')
})

test('clearing the date removes the previous report and does not request or invent another date', async () => {
  const calls = []
  const { state, mount } = page(async path => { calls.push(path); return report })
  await mount()
  state.day.value = ''
  await state.loadReport()
  await state.moveDay(1)
  assert.equal(state.report.value, null)
  assert.equal(calls.length, 1)
  assert.match(state.error.value, /Wybierz/)
  assert.equal(state.readableDay.value, 'Wybierz dzień')
})
