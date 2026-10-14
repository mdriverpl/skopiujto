import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./EDeliveryPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'edelivery-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, confirm = () => true) {
  const mounted = [], context = { computed, ref, EDeliverySettings: {}, onMounted: fn => mounted.push(fn), window: { confirm } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api }, { expose() {} })
  return { state, mount: () => mounted[0]() }
}
const record = { id: 'one', title: 'Pismo', correspondent: 'Urząd', address: 'AE:123', reference: 'REF-1', direction: 'incoming', status: 'registered', record_date: '2026-10-14', notes: 'Odpowiedź', version: 1, created_at: '2026-10-14T10:00:00Z' }

test('register loads and combines search, direction and status filters', async () => {
  const { state, mount } = panel(async path => { if (path === '/edeliveries/connection') return { enabled: false }; assert.equal(path, '/edeliveries'); return [record, { ...record, id: 'two', direction: 'outgoing', status: 'sent' }] })
  await mount()
  assert.equal(state.loaded.value, true)
  state.search.value = 'ae:123'
  assert.equal(state.filtered.value.length, 2)
  state.direction.value = 'incoming'
  assert.equal(state.filtered.value.length, 1)
  state.status.value = 'sent'
  assert.equal(state.filtered.value.length, 0)
})
test('new entry stays a draft until saved and is persisted through API', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => { calls.push({ path, method, body }); return { ...record, ...body } })
  state.edit()
  assert.match(state.draft.value.record_date, /^\d{4}-\d{2}-\d{2}$/)
  assert.equal(calls.length, 0)
  state.draft.value.title = ' Pismo '
  state.draft.value.correspondent = ' Urząd '
  await state.save()
  assert.equal(calls[0].path, '/edeliveries')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].body.title, 'Pismo')
  assert.equal(state.draft.value, null)
  assert.equal(state.records.value.length, 1)
})
test('edit conflict preserves draft and sends original version', async () => {
  let request
  const { state } = panel(async (path, method, body) => { request = { path, method, body }; throw new Error('Przesyłka została zmieniona') })
  state.edit(record); state.draft.value.notes = 'Moje zmiany'
  await state.save()
  assert.equal(request.path, '/edeliveries/one')
  assert.equal(request.method, 'PATCH')
  assert.equal(request.body.version, 1)
  assert.equal(record.notes, 'Odpowiedź')
  assert.equal(state.draft.value.notes, 'Moje zmiany')
  assert.match(state.error.value, /zmieniona/)
  assert.equal(state.busy.value, false)
})
test('cancelled or failed deletion keeps entry; confirmed deletion removes it', async () => {
  const { state } = panel(async () => { throw new Error('Błąd zapisu') })
  state.records.value = [record]
  await state.remove(record)
  assert.equal(state.records.value.length, 1)
  let calls = 0
  const cancelled = panel(async () => { calls++ }, () => false).state
  cancelled.records.value = [record]
  await cancelled.remove(record)
  assert.equal(calls, 0)
  const successful = panel(async (path, method) => { assert.equal(path, '/edeliveries/one'); assert.equal(method, 'DELETE') }).state
  successful.records.value = [record]
  await successful.remove(record)
  assert.equal(successful.records.value.length, 0)
})
test('pending save blocks repeated submissions and keeps draft until completed', async () => {
  let complete, calls = 0
  const { state } = panel(() => { calls++; return new Promise(resolve => { complete = resolve }) })
  state.edit(record)
  const pending = state.save()
  await state.save()
  assert.equal(calls, 1)
  assert.equal(state.busy.value, true)
  complete({ ...record, version: 2 })
  await pending
  assert.equal(state.draft.value, null)
  assert.equal(state.records.value[0].version, 2)
})

test('sync refreshes records and reports the recent-message scope', async () => {
  const calls = []
  const { state } = panel(async (path, method) => {
    calls.push({ path, method })
    if (path === '/edeliveries/sync') return { message: 'Synchronizacja zakończona', more: true }
    if (path === '/edeliveries/connection') return { enabled: true }
    return [{ ...record, message_id: 'remote-id' }]
  })
  await state.sync()
  assert.equal(calls[0].path, '/edeliveries/sync')
  assert.equal(calls[0].method, 'POST')
  assert.equal(state.records.value[0].message_id, 'remote-id')
  assert.match(state.notice.value, /starsze/)
  state.edit(state.records.value[0])
  assert.equal(state.draft.value, null)
})
