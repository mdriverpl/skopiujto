import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref, computed } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./SurveysPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'surveys-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { ref, computed, onMounted() {}, onBeforeUnmount() {}, setInterval() {}, clearInterval() {}, crypto: { randomUUID: () => 'request_1234567890' }, window: { confirm: () => true } }
  runInNewContext(compiled, context)
  return context.component.setup({ api }, { expose() {}, emit() {} })
}

test('filters and counters follow visible surveys without mixing own and assigned', () => {
  const state = panel(async () => [])
  state.surveys.value = [
    { title: 'Spotkanie', description: '', assigned: true, is_owner: false, expected: 4, completed: 1 },
    { title: 'Inna ankieta', description: '', assigned: false, is_owner: true, expected: 2, completed: 2 },
  ]
  assert.equal(state.totals.value.expected, 6)
  state.filter.value = 'mine'; assert.equal(state.visible.value.length, 1)
  assert.equal(state.totals.value.completed, 1)
  state.filter.value = 'sent'; assert.equal(state.totals.value.completed, 2)
  state.search.value = 'SPOTKANIE'; assert.equal(state.visible.value.length, 0)
})

test('creation validates choices before API and sends exact questions and recipients', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { calls.push({ path, method, body }); return [] })
  state.title.value = 'Ankieta'; state.selected.value = ['one']; state.addQuestion()
  Object.assign(state.questions.value[0], { label: 'Termin', type: 'select', optionsText: 'Tak\nTak' })
  await state.create(); assert.equal(calls.length, 0)
  state.questions.value[0].optionsText = 'Tak\nNie'
  await state.create()
  assert.equal(calls[0].path, '/surveys'); assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].body.questions[0].options.length, 2)
  assert.equal(calls[0].body.recipients[0], 'one')
})

test('owner who answered sees their own response, not another recipient response', async () => {
  const state = panel(async () => ({ id: 'survey', assigned: true, submitted_at: '2030-01-01', is_owner: true, questions: [{ id: 'q', type: 'text' }], responses: [
    { is_me: false, submitted_at: '2030-01-01', answers: { q: 'Someone else' } },
    { is_me: true, submitted_at: '2030-01-01', answers: { q: 'My answer' } },
  ] }))
  await state.openSurvey({ id: 'survey' })
  assert.equal(state.answers.value.q, 'My answer')
  assert.equal(state.canSubmit.value, false)
})

test('submission is guarded after success and retains draft after validation error', async () => {
  let calls = 0
  const state = panel(async () => { calls++; throw Error('Uzupełnij pole') })
  state.current.value = { id: 'survey', assigned: true, submitted_at: null, closed_at: null }
  state.answers.value = { q: 'Draft' }
  await state.submit(); assert.equal(state.answers.value.q, 'Draft'); assert.equal(state.busy.value, false)
  state.current.value.submitted_at = '2030-01-01'
  await state.submit(); assert.equal(calls, 1)
})

test('statistics count only submitted responses and keep false checkbox answers', () => {
  const state = panel(async () => [])
  state.current.value = { responses: [
    { submitted_at: '2030-01-01', answers: { q: true } },
    { submitted_at: '2030-01-01', answers: { q: false } },
    { submitted_at: null, answers: null },
  ] }
  const results = state.distributions({ id: 'q', type: 'checkbox' })
  assert.equal(results[0].count, 1); assert.equal(results[1].count, 1); assert.equal(results[0].total, 2)
  assert.equal(state.showAnswer(false), 'Nie')
})

test('refreshing statistics preserves an unfinished answer', async () => {
  const state = panel(async path => path === '/surveys' ? [] : { id: 'survey', assigned: true, submitted_at: null, closed_at: null, responses: [], completed: 2 })
  state.current.value = { id: 'survey', assigned: true, submitted_at: null }
  state.answers.value = { q: 'Unsent text' }
  await state.refreshCurrent()
  assert.equal(state.current.value.completed, 2)
  assert.equal(state.answers.value.q, 'Unsent text')
})

test('survey can be saved without choosing recipients or sending messages', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { calls.push({ path, method, body }); return [] })
  await state.newSurvey()
  assert.equal(calls.length, 0)
  state.title.value = 'Draft'; state.questions.value[0].label = 'Question'
  await state.create()
  assert.equal(calls[0].path, '/surveys')
  assert.equal(calls[0].body.recipients.length, 0)
  assert.equal(state.creating.value, false)
})

test('dictionary import uses selected channel and chosen contacts, deduplicates recipients', async () => {
  const state = panel(async path => path === '/dictionaries' ? [{ id: 'clients', name: 'Klienci' }] : [
    { id: 'd:one', name: 'Anna', channels: { email: 'anna@example.com', sms: '+48600123456' } },
    { id: 'd:two', name: 'Jan', channels: { sms: '+48600234567' } },
  ])
  await state.openSend({ id: 'survey' }); state.selectedDictionary.value = 'clients'
  await state.loadDictionary()
  assert.equal(state.availableContacts.value.length, 1)
  state.chosenContacts.value = ['d:one']; state.importContacts(); state.chosenContacts.value = ['d:one']; state.importContacts()
  assert.equal(state.sendPeople.value.length, 1); assert.equal(state.sendPeople.value[0].address, 'anna@example.com')
  state.sendPeople.value = []; state.sendChannel.value = 'sms'; state.chosenContacts.value = ['d:two']; state.importContacts()
  assert.equal(state.sendPeople.value[0].address, '+48600234567')
})

test('failed send retains same request ID so a repeated attempt cannot resend a batch', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { if (method) { calls.push(body); throw Error('Network interrupted') } return [] })
  await state.openSend({ id: 'survey' }); state.sendPeople.value = [{ name: 'Anna', address: 'anna@example.com' }]
  await state.sendInvites(); await state.sendInvites()
  assert.equal(calls[0].request_id, calls[1].request_id)
  assert.equal(state.sendingSurvey.value.id, 'survey')
})
