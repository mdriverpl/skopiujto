import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import { fieldKey } from './documentFields.js'

const compiled = compileScript(parse(readFileSync(new URL('./AiDataPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'ai-data-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const mounted = [], context = { computed, ref, fieldKey, onMounted: callback => mounted.push(callback), window: { confirm: () => true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api }, { expose() {} })
  return { state, mount: () => mounted[0]() }
}
const saved = { id: 'one', name: 'Moja firma', version: 1,
  fields: { 'miejsce zawarcia umowy': 'Warszawa', 'adres zamawiającego': 'Długa 1' } }

test('AI lists existing saved data and searches names, fields and values', async () => {
  const { state, mount } = panel(async path => { assert.equal(path, '/saved-data'); return [saved] })
  await mount()
  assert.equal(state.profiles.value.length, 1)
  assert.equal(state.fieldCount.value, 2)
  for (const query of ['MOJA', 'ZAMAWIAJĄCEGO', 'warszawa']) {
    state.search.value = query
    assert.equal(state.filtered.value.length, 1)
  }
  state.search.value = 'Nie istnieje'
  assert.equal(state.filtered.value.length, 0)
})

test('adding a set sends normalized fields to the same API used by documents', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return { ...body, id: 'new', version: 1 }
  })
  state.open()
  state.draft.value.rows[0].label = '  Adres   Zamawiającego '
  state.draft.value.rows[0].value = 'Długa 1'
  state.addRow()
  state.draft.value.rows[1].label = 'miejsce zawarcia umowy'
  state.draft.value.rows[1].value = 'Warszawa'
  state.addRow() // Entirely blank extra row is ignored.
  await state.save()
  assert.equal(calls[0].path, '/saved-data')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].body.name, Object.keys(calls[0].body.fields)[0])
  assert.equal(calls[0].body.fields['adres zamawiającego'], 'Długa 1')
  assert.equal(Object.keys(calls[0].body.fields).length, 2)
  assert.equal(state.profiles.value.length, 1)
  assert.equal(state.draft.value, null)
})

test('editing updates original ID and allows removal of saved fields without mutating original', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return { ...body, id: saved.id, version: 2 }
  })
  state.profiles.value = [saved]
  state.open(saved)
  state.removeRow(state.draft.value.rows[1].id)
  state.draft.value.rows[0].value = 'Kraków'
  assert.equal(saved.fields['miejsce zawarcia umowy'], 'Warszawa')
  await state.save()
  assert.equal(calls[0].path, '/saved-data/one')
  assert.equal(calls[0].method, 'PUT')
  assert.equal(calls[0].body.version, 1)
  assert.equal(Object.keys(calls[0].body.fields).length, 1)
  assert.equal(state.profiles.value.length, 1)
})

test('duplicate names, incomplete fields and placeholders are blocked before request', async () => {
  let requests = 0
  const { state } = panel(async () => { requests++ })
  state.open()
  state.draft.value.rows[0].label = 'Adres'
  state.draft.value.rows[0].value = 'Długa 1'
  state.addRow()
  state.draft.value.rows[1].label = ' adres '
  state.draft.value.rows[1].value = 'Krótka 2'
  await state.save()
  assert.match(state.formError.value, /powtarza/)
  state.draft.value.rows[1].label = '[miasto]'
  await state.save()
  assert.match(state.formError.value, /nawiasów/)
  state.draft.value.rows[1].label = 'miasto'
  state.draft.value.rows[1].value = ''
  await state.save()
  assert.match(state.formError.value, /nazwę i wartość/)
  assert.equal(requests, 0)
})

test('failed save keeps entered data; confirmed deletion removes only selected set', async () => {
  const calls = []
  const { state } = panel(async (path, method) => {
    calls.push({ path, method }); if (method === 'PUT') throw new Error('Zestaw został zmieniony')
  })
  state.profiles.value = [saved]
  state.open(saved)
  state.draft.value.rows[0].value = 'Kraków'
  await state.save()
  assert.equal(state.draft.value.rows[0].value, 'Kraków')
  assert.equal(state.formError.value, 'Zestaw został zmieniony')
  state.close()
  await state.remove()
  assert.equal(calls.length, 1)
  state.confirmRemoval(saved)
  await state.remove()
  assert.equal(calls[1].path, '/saved-data/one')
  assert.equal(calls[1].method, 'DELETE')
  assert.equal(state.profiles.value.length, 0)
})

test('a pending save blocks duplicate requests and row edits; failures preserve delete dialog', async () => {
  let resolve, requests = 0
  const { state } = panel(async (_path, method, body) => {
    requests++
    if (method === 'DELETE') throw new Error('Brak połączenia')
    return new Promise(done => { resolve = () => done({ ...body, id: 'one', version: 2 }) })
  })
  state.open(saved)
  const pending = state.save()
  await state.save()
  state.addRow()
  assert.equal(requests, 1)
  assert.equal(state.draft.value.rows.length, 2)
  resolve(); await pending
  state.confirmRemoval(saved)
  await state.remove()
  assert.equal(state.deleting.value.id, 'one')
  assert.equal(state.formError.value, 'Brak połączenia')
  assert.equal(state.profiles.value.length, 1)
})
