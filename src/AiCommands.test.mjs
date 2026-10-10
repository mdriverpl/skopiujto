import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref, computed } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./AiCommands.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'commands-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { ref, computed, onMounted() {}, onBeforeUnmount() {}, setInterval() {}, clearInterval() {} }
  runInNewContext(compiled, context)
  return context.component.setup({ api }, { expose() {} })
}
const config = { ai: { available: true }, dictionaries: [] }
const plan = { id: 'one', action: 'message', subject: 'Spotkanie', message: 'Sala 19:00',
  recipients: [{ id: 'user', available: true }, { id: 'missing', available: false, reason: 'Brak adresu' }] }
test('preparing selects both sources, only available recipients and does not execute', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { calls.push({ path, method, body }); return plan })
  state.options.value = config; state.prompt.value = 'Wyślij spotkanie 19:00'
  await state.prepare()
  assert.equal(calls.length, 1); assert.equal(calls[0].body.source, 'both')
  assert.equal(calls[0].path, '/ai/commands/plan'); assert.equal(state.chosen.value.length, 1)
})
test('explicit send uses reviewed content and selected IDs then opens history', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (method) return { recipients: [{ status: 'sent' }] }
    return path.endsWith('options') ? config : []
  })
  state.plan.value = { ...plan, message: 'Zmieniona wiadomość' }; state.chosen.value = ['user']
  await state.execute()
  assert.equal(calls[0].path, '/ai/commands/one/execute')
  assert.equal(calls[0].body.confirmed, true)
  assert.equal(calls[0].body.message, 'Zmieniona wiadomość')
  assert.equal(state.plan.value, null); assert.equal(state.tab.value, 'history')
})
test('missing configuration and send failures preserve input and selected recipients', async () => {
  let calls = 0
  const state = panel(async () => { calls++; throw new Error('Serwer odrzucił wysyłkę') })
  state.prompt.value = 'Spotkanie'; await state.prepare(); assert.equal(calls, 0)
  state.plan.value = plan; state.chosen.value = ['user']; await state.execute()
  assert.equal(state.plan.value.message, 'Sala 19:00'); assert.equal(state.chosen.value[0], 'user')
  assert.equal(state.busy.value, false)
})
test('reading a message updates unread count through authenticated inbox endpoint', async () => {
  const state = panel(async path => { assert.equal(path, '/messages/message/read'); return { read_at: '2030-01-01T10:00:00Z' } })
  state.messages.value = [{ id: 'message', read_at: null }]
  assert.equal(state.unread.value, 1)
  await state.markRead(state.messages.value[0]); assert.equal(state.unread.value, 0)
})

test('list combines sent and received, skips excluded recipients and filters actual send dates', () => {
  const state = panel(async () => [])
  state.history.value = [{ id: 'job', subject: 'Spotkanie', message: 'Sala 19:00', created_at: '2000-01-01T12:00:00Z', sent_at: '2030-06-15T12:00:00Z', recipients: [
    { id: 'anna', name: 'Anna', address: 'anna@example.com', channel: 'email', status: 'sent' },
    { id: 'skip', name: 'Skip', status: 'skipped' },
  ] }]
  state.messages.value = [{ id: 'inbox', sender_name: 'Jan', subject: 'Inne', message: 'Treść', created_at: '2030-06-14T12:00:00Z' }]
  assert.equal(state.tab.value, 'all'); assert.equal(state.filteredRows.value.length, 2)
  state.recipientFilter.value = 'ANNA@'; state.descriptionFilter.value = '19:00'
  state.fromDate.value = '2030-06-15'; state.toDate.value = '2030-06-15'
  assert.equal(state.filteredRows.value.length, 1)
  state.tab.value = 'inbox'; assert.equal(state.filteredRows.value.length, 0)
})

test('manual preview needs no AI and keeps recipients hidden by text search', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { calls.push({ path, body }); return plan })
  state.subject.value = 'Spotkanie'; state.body.value = 'Sala 19:00'
  state.contacts.value = [{ id: 'u:one', name: 'Anna', source: 'Użytkownicy' }, { id: 'd:two', name: 'Jan', source: 'Klienci', dictionary_id: 'clients' }]
  state.selected.value = ['u:one', 'd:two']; state.contactSearch.value = 'Anna'
  await state.prepareManual()
  assert.equal(calls[0].path, '/messages/prepare')
  assert.equal(calls[0].body.recipients.length, 2)
  assert.equal(state.chosen.value.length, 1)
})
