import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./NotesPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'notes-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, props = {}) {
  const events = [], mounted = [], context = { computed, ref, watch, onMounted: fn => mounted.push(fn), window: { confirm: () => true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, ...props }, { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, mount: () => mounted[0]() }
}
const note = { id: 'one', title: 'Ustalenia', content: 'Oferta w piątek', version: 1, updated_at: '2030-01-01T10:00:00Z' }

test('AI draft requires a manual save and is posted as a new personal note', async () => {
  const calls = []
  const { state, events } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return { ...note, ...body }
  }, { initialDraft: { title: note.title, content: note.content } })
  assert.equal(calls.length, 0)
  assert.deepEqual(events, [['draft-consumed']])
  assert.equal(state.editor.value.content, note.content)
  await state.save()
  assert.equal(calls[0].path, '/notes')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].body.content, note.content)
  assert.equal(state.editor.value, null)
  assert.equal(state.notes.value.length, 1)
})

test('editing includes version and conflict keeps the unsaved text', async () => {
  let request
  const { state } = panel(async (path, method, body) => {
    request = { path, method, body }; throw new Error('Notatka została zmieniona')
  })
  state.edit(note)
  state.editor.value.content = 'Moje zmiany'
  await state.save()
  assert.equal(request.path, '/notes/one')
  assert.equal(request.method, 'PATCH')
  assert.equal(request.body.version, 1)
  assert.equal(state.editor.value.content, 'Moje zmiany')
  assert.match(state.error.value, /zmieniona/)
  assert.equal(state.busy.value, false)
})

test('search finds note contents and successful deletion updates the list', async () => {
  const { state } = panel(async () => undefined)
  state.notes.value = [note, { ...note, id: 'two', title: 'Inna', content: 'Zakupy' }]
  state.search.value = 'PIĄTEK'
  assert.equal(state.filtered.value.length, 1)
  await state.remove(note)
  assert.equal(state.notes.value.length, 1)
  assert.equal(state.filtered.value.length, 0)
})


test('content-only notes generate a title and blank content cannot be saved', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => { calls.push(body); return { ...note, ...body } })
  state.edit()
  state.editor.value.content = '   '
  await state.save()
  assert.equal(calls.length, 0)
  state.editor.value.content = 'First line\nMore details'
  await state.save()
  assert.equal(calls[0].title, 'First line')
  assert.equal(calls[0].content, 'First line\nMore details')
  state.edit({ ...note, content: '' })
  assert.equal(state.editor.value.content, note.title)
})
