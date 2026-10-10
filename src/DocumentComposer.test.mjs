import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch, nextTick } from 'vue'
import { documentFields, documentText, fillDocument, plainDocument } from './documentFields.js'

const compiled = compileScript(parse(readFileSync(new URL('./DocumentComposer.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'composer-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')

function composer(props) {
  const events = [], mounted = [], unmounted = [], timers = new Map(), context = { computed, ref, watch, documentFields, documentText, fillDocument,
    plainDocument, RichTextEditor: {}, crypto: { randomUUID: () => 'draft-test' },
    setTimeout: callback => { const id = timers.size + 1; timers.set(id, callback); return id },
    clearTimeout: id => timers.delete(id), onBeforeUnmount: callback => unmounted.push(callback),
    onMounted: callback => mounted.push(callback) }
  runInNewContext(compiled, context)
  const state = context.component.setup({ editable: true, ...props }, { expose() {}, emit: (...args) => events.push(args) })
  mounted.forEach(callback => callback())
  return { state, events, destroy: () => unmounted.forEach(callback => callback()) }
}

test('contract defaults to preview with fields and emits both filled content and reusable source', async () => {
  const original = plainDocument('Sprzedający: [sprzedający]. Cena: [cena]')
  const { state, events } = composer({ modelValue: original })
  assert.equal(state.mode.value, 'fill')
  state.values.value.sprzedający = 'Anna'
  state.values.value.cena = '1000 zł'
  await nextTick()
  assert.equal(state.completed.value, 2)
  assert.equal(events.findLast(event => event[0] === 'update:plainText')[1], 'Sprzedający: Anna. Cena: 1000 zł')
  assert.equal(documentText(events.findLast(event => event[0] === 'update:fieldSource')[1]), documentText(original))
  assert.equal(events.findLast(event => event[0] === 'update:fieldValues')[1].cena, '1000 zł')
})

test('reopening restores fields even when saved content has no placeholders', () => {
  const original = plainDocument('Cena: [cena]')
  const { state } = composer({ modelValue: plainDocument('Cena: 1000 zł'), fieldSource: original, fieldValues: { cena: '1000 zł' } })
  assert.equal(state.fields.value.length, 1)
  assert.equal(state.values.value.cena, '1000 zł')
  assert.equal(documentText(state.result.value), 'Cena: 1000 zł')
})

test('removing a placeholder drops obsolete saved data', async () => {
  const { state, events } = composer({ modelValue: plainDocument('Cena: [cena]. Data: [data]'), fieldValues: { cena: '1000', data: '10.10.2026' } })
  state.source.value = plainDocument('Cena: [cena]')
  await nextTick()
  const values = events.findLast(event => event[0] === 'update:fieldValues')[1]
  assert.equal(values.cena, '1000')
  assert.equal('data' in values, false)
})

test('readonly preview does not emit document changes', async () => {
  const { state, events } = composer({ editable: false, modelValue: plainDocument('Cena: [cena]') })
  state.values.value.cena = '1000 zł'
  await nextTick()
  assert.equal(events.length, 0)
})

test('AI automatically fills matching empty fields using semantic results without copying them to memory', async () => {
  const calls = []
  const { state } = composer({ modelValue: plainDocument('[miejsce podpisania], [adres zamawiającego]'),
    fieldValues: { 'adres zamawiającego': 'Wpisany adres' }, title: 'Umowa', api: async (path, method, body) => {
      calls.push({ path, method, body })
      return { matches: { 'miejsce podpisania': { value: 'Warszawa', source: 'Dane: Umowa' },
        'adres zamawiającego': { value: 'Nie nadpisuj', source: 'Firma' }, 'nieznane': { value: 'x' } } }
    } })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls[0].path, '/saved-data/match')
  assert.equal(calls[0].body.fields.join(), 'miejsce podpisania')
  assert.equal(state.values.value['miejsce podpisania'], 'Warszawa')
  assert.equal(state.values.value['adres zamawiającego'], 'Wpisany adres')
  assert.equal('nieznane' in state.values.value, false)
  assert.equal(state.autoSources.value['miejsce podpisania'], 'Dane: Umowa')
  await state.flushMemory()
  assert.equal(calls.length, 1)
})

test('manual edits save automatically to one document memory and obsolete values are excluded', async () => {
  const calls = []
  const { state } = composer({ documentId: 'doc-one', title: 'Sprzedaż', modelValue: plainDocument('[adres sprzedającego]'),
    fieldValues: { 'obsolete': 'Nie zapisuj' }, api: async (path, method, body) => { calls.push({ path, method, body }); return {} } })
  state.values.value['adres sprzedającego'] = 'Długa 1'
  state.recordManual('adres sprzedającego')
  await state.flushMemory()
  assert.equal(calls[0].path, '/saved-data/match')
  assert.equal(calls[1].path, '/saved-data/remember')
  assert.equal(calls[1].body.source_key, 'doc-one')
  assert.equal(calls[1].body.fields['adres sprzedającego'], 'Długa 1')
  assert.equal('obsolete' in calls[1].body.fields, false)
  state.values.value['adres sprzedającego'] = 'Długa 2'
  state.recordManual('adres sprzedającego')
  await state.flushMemory()
  assert.equal(calls[2].body.source_key, 'doc-one')
  assert.equal(calls[2].body.fields['adres sprzedającego'], 'Długa 2')
})

test('late AI result cannot overwrite a user edit or fill other fields based on stale identity', async () => {
  let finish
  const { state } = composer({ modelValue: plainDocument('[nazwa sprzedającego], [adres sprzedającego]'),
    api: () => new Promise(resolve => { finish = resolve }) })
  state.values.value['nazwa sprzedającego'] = 'Nowa firma'
  state.recordManual('nazwa sprzedającego')
  finish({ matches: { 'adres sprzedającego': { value: 'Adres innej firmy', source: 'Stare dane' } } })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.values.value['nazwa sprzedającego'], 'Nowa firma')
  assert.equal(state.values.value['adres sprzedającego'], undefined)
})

test('cleared fields remain blank and unavailable AI does not stop manual saving', async () => {
  const calls = []
  const { state } = composer({ modelValue: plainDocument('[miasto]'), api: async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.endsWith('/match')) throw new Error('Brak klucza AI')
    return {}
  } })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.matchError.value, 'Brak klucza AI')
  state.values.value.miasto = 'Warszawa'
  state.recordManual('miasto')
  await state.flushMemory()
  assert.equal(calls[1].path, '/saved-data/remember')
  state.clearFields()
  await state.matchFields()
  assert.equal(calls.length, 2)
  assert.equal(state.values.value.miasto, undefined)
})

test('failed memory save preserves data for retry and closing flushes pending manual changes', async () => {
  let fail = true
  const calls = []
  const { state, destroy } = composer({ modelValue: plainDocument('[miasto]'), api: async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.endsWith('/remember') && fail) throw new Error('Brak połączenia')
    return { matches: {} }
  } })
  state.values.value.miasto = 'Warszawa'; state.recordManual('miasto')
  await state.flushMemory()
  assert.match(state.memoryError.value, /Brak połączenia/)
  assert.equal(state.values.value.miasto, 'Warszawa')
  fail = false; destroy()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(calls.filter(call => call.path.endsWith('/remember')).length, 2)
  assert.equal(state.memoryError.value, '')
})

test('readonly preview neither matches nor saves private data', async () => {
  let calls = 0
  const { state, destroy } = composer({ editable: false, modelValue: plainDocument('[miasto]'), api: async () => { calls++; return {} } })
  state.values.value.miasto = 'Warszawa'; state.recordManual('miasto')
  await state.flushMemory(); await state.matchFields(); destroy()
  assert.equal(calls, 0)
})

test('changing party identity invalidates prior AI values while preserving manual entries', async () => {
  const { state } = composer({ modelValue: plainDocument('[nazwa sprzedającego], [adres sprzedającego], [cena]'),
    fieldValues: { cena: '1000' }, api: async () => ({ matches: {
      'adres sprzedającego': { value: 'Adres firmy Alfa', source: 'Alfa' } } }) })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.values.value['adres sprzedającego'], 'Adres firmy Alfa')
  state.values.value['nazwa sprzedającego'] = 'Firma Beta'
  state.recordManual('nazwa sprzedającego')
  assert.equal(state.values.value['adres sprzedającego'], undefined)
  assert.equal(state.values.value.cena, '1000')
})

