import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import { fieldKey } from './documentFields.js'
const compiled = compileScript(parse(readFileSync(new URL('./DictionariesPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'dictionaries-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { computed, ref, fieldKey, AiDataPanel: {}, ExcelTransfer: {}, onMounted() {}, window: { confirm: () => true } }
  runInNewContext(compiled, context)
  return context.component.setup({ api }, { expose() {} })
}
const dictionary = { id: 'employees', name: 'Pracownicy', fields: ['Imię', 'Nazwisko'], count: 0, version: 1 }
test('tiles count existing AI data and open dictionary columns with search', async () => {
  const state = panel(async path => path === '/dictionaries' ? [dictionary] : path === '/saved-data' ? [{ fields: { city: 'Warsaw' } }] :
    { dictionary, entries: [{ id: 'one', values: { 'Imię': 'Anna', 'Nazwisko': 'Kowalska' } }] })
  await state.load(); assert.equal(state.aiCount.value, 1)
  await state.open({ id: 'ai' }); assert.equal(state.selected.value.id, 'ai')
  await state.open(dictionary); assert.equal(state.selected.value.fields[0], 'Imię')
  state.search.value = 'kowal'; assert.equal(state.filtered.value.length, 1)
  state.search.value = 'missing'; assert.equal(state.filtered.value.length, 0)
})
test('creating a dictionary preserves its labels and entries use its schema with versioned edits', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    return path === '/dictionaries' ? { ...dictionary } : { id: 'one', values: body.values, version: 2 }
  })
  state.newDictionary(); state.draft.value.name = 'Pracownicy'; state.draft.value.fields = ['Imię', 'Nazwisko']
  await state.saveDictionary(); assert.equal(state.selected.value.name, 'Pracownicy')
  state.editRecord(); state.record.value.values['Imię'] = 'Anna'; await state.saveRecord()
  assert.equal(calls[1].method, 'POST'); assert.equal(calls[1].body.values['Imię'], 'Anna')
  state.editRecord(state.entries.value[0]); state.record.value.values['Nazwisko'] = 'Kowalska'; await state.saveRecord()
  assert.equal(calls[2].method, 'PUT'); assert.equal(calls[2].body.version, 2)
  assert.equal(state.entries.value.length, 1)
})
test('failed dictionary creation and record edits retain entered values', async () => {
  const state = panel(async () => { throw new Error('Brak połączenia') })
  state.newDictionary(); state.draft.value.name = 'Pracownicy'; await state.saveDictionary()
  assert.equal(state.draft.value.name, 'Pracownicy'); assert.equal(state.busy.value, false)
  state.selected.value = dictionary; state.editRecord(); state.record.value.values['Imię'] = 'Anna'
  await state.saveRecord(); assert.equal(state.record.value.values['Imię'], 'Anna')
  assert.equal(state.formError.value, 'Brak połączenia')
})

test('schema editor maps renamed fields, keeps new fields separate and replaces table after saving', async () => {
  const calls = []
  const updated = { ...dictionary, fields: ['Imię pracownika', 'Telefon'], version: 2 }
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return { dictionary: updated, entries: [{ id: 'one', values: { 'Imię pracownika': 'Anna', Telefon: '' }, version: 2 }] }
  })
  state.dictionaries.value = [dictionary]
  state.editDictionary(dictionary)
  state.draft.value.fields[0] = 'Imię pracownika'
  state.removeField(1); state.addField(); state.draft.value.fields[1] = 'Telefon'
  assert.equal(state.removedFields.value[0], 'Nazwisko')
  assert.equal(dictionary.fields[0], 'Imię')
  await state.saveDictionary()
  assert.equal(calls[0].method, 'PUT')
  assert.equal(calls[0].path, '/dictionaries/employees')
  assert.equal(calls[0].body.version, 1)
  assert.equal(calls[0].body.field_sources['Imię pracownika'], 'Imię')
  assert.equal(calls[0].body.field_sources.Telefon, null)
  assert.equal(state.entries.value[0].values['Imię pracownika'], 'Anna')
  assert.equal(state.dictionaries.value.length, 1)
  assert.equal(state.draft.value, null)
})

test('AI cannot open schema editor and failed schema saves preserve draft and source values', async () => {
  const state = panel(async () => { throw new Error('Słownik został zmieniony') })
  state.editDictionary({ id: 'ai' }); assert.equal(state.draft.value, null)
  state.editDictionary(dictionary); state.draft.value.fields[0] = 'Nowe imię'
  await state.saveDictionary()
  assert.equal(state.draft.value.fields[0], 'Nowe imię')
  assert.equal(state.draft.value.sources[0], 'Imię')
  assert.equal(state.formError.value, 'Słownik został zmieniony')
})

test('a dictionary opened before version support fetches its version while retaining entered changes', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    return { dictionary: { ...dictionary, version: method ? 2 : 1 }, entries: [] }
  })
  state.editDictionary({ ...dictionary, version: undefined })
  state.draft.value.fields[0] = 'Imię pracownika'
  await state.saveDictionary()
  assert.equal(calls[0].path, '/dictionaries/employees/entries')
  assert.equal(calls[1].method, 'PUT')
  assert.equal(calls[1].body.version, 1)
  assert.equal(calls[1].body.fields[0], 'Imię pracownika')
})

test('missing version does not overwrite a changed schema and invalid fields stay in the form', async () => {
  let posts = 0
  const state = panel(async (path, method) => {
    if (method) posts++
    return { dictionary: { ...dictionary, fields: ['Inne pole'], version: 2 } }
  })
  state.editDictionary({ ...dictionary, version: undefined })
  await state.saveDictionary()
  assert.match(state.formError.value, /Słownik został zmieniony/)
  assert.equal(posts, 0)
  state.draft.value.fields = ['Imię', ' imię ']
  await state.saveDictionary()
  assert.match(state.formError.value, /powtarzać/)
  state.draft.value.fields = ['']
  await state.saveDictionary()
  assert.match(state.formError.value, /puste pole/)
  assert.equal(posts, 0)
})
