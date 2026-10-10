import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, toRaw, reactive } from 'vue'

// Exercise the actual component's save handler without mounting the text editor.
const source = readFileSync(new URL('./TemplatesPanel.vue', import.meta.url), 'utf8')
const compiled = compileScript(parse(source).descriptor, { id: 'template-save-test' }).content
  .replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')

function panel(api) {
  const context = { computed, ref, toRaw, structuredClone, RichTextEditor: {}, AiPrompt: {} }
  runInNewContext(compiled, context)
  const calls = [], events = []
  const state = context.component.setup({ templates: [], canAdd: true,
    api: async (...args) => { calls.push(args); return api ? api(...args) : {} }
  }, { expose() {}, emit: (...args) => events.push(args) })
  return { state, calls, events }
}

for (const owner of ['me', null]) {
  test(`editing ${owner === null ? 'builtin' : 'own'} template updates the original ID`, async () => {
    const { state, calls, events } = panel()
    state.open(reactive({ id: 'existing-template', user_id: owner, version: 4,
      title: 'Umowa', category: 'Umowy', description: '', content: 'Treść', rich_content: null }), 'edit')
    state.draft.value.title = 'Zmieniona umowa'
    await state.save()
    assert.equal(calls.length, 1)
    assert.equal(calls[0][0], '/templates/existing-template')
    assert.equal(calls[0][1], 'PUT')
    assert.equal(calls[0][2].version, 4)
    assert.equal(calls[0][2].title, 'Zmieniona umowa')
    assert.equal(events[0][0], 'updated')
  })
}

test('only an explicit copy or new template uses POST', async () => {
  const { state, calls } = panel()
  state.open({ id: 'source-template', version: 1, title: 'Umowa', content: 'Treść', rich_content: null }, 'copy')
  await state.save()
  assert.equal(calls[0][0], '/templates')
  assert.equal(calls[0][1], 'POST')
  assert.equal(calls[0][2].version, undefined)
  state.create()
  state.draft.value.title = 'Nowy wzór'
  await state.save()
  assert.equal(calls[1][1], 'POST')
})

test('preview never saves a copy on form submission', async () => {
  const { state, calls } = panel()
  state.open({ id: 'source-template', title: 'Umowa', content: 'Treść', rich_content: null })
  await state.save()
  assert.equal(calls.length, 0)
})

test('confirmed deletion removes the selected template and refreshes the list', async () => {
  const { state, calls, events } = panel()
  state.deleting.value = { id: 'selected-template', permissions: { delete: true } }
  await state.remove()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], '/templates/selected-template')
  assert.equal(calls[0][1], 'DELETE')
  assert.equal(state.deleting.value, null)
  assert.equal(events[0][0], 'updated')
})

test('failed deletion keeps the confirmation open and does not report success', async () => {
  const { state, events } = panel(async () => { throw new Error('Brak uprawnienia') })
  state.deleting.value = { id: 'selected-template', permissions: { delete: true } }
  await state.remove()
  assert.equal(state.deleting.value.id, 'selected-template')
  assert.equal(state.error.value, 'Brak uprawnienia')
  assert.equal(state.busy.value, false)
  assert.equal(events.length, 0)
})

test('deletion is skipped without a confirmed selection or delete permission', async () => {
  const { state, calls } = panel()
  await state.remove()
  state.deleting.value = { id: 'selected-template', permissions: { delete: false } }
  await state.remove()
  assert.equal(calls.length, 0)
})

test('AI opens an unsaved new template and saves only after review', async () => {
  const { state, calls } = panel()
  state.aiDialog.value = true
  state.generatedTemplate({ title: 'Wzór AI', category: 'Inne', description: '', content: 'Treść AI', rich_content: null })
  assert.equal(calls.length, 0)
  assert.equal(state.aiDialog.value, false)
  assert.equal(state.mode.value, 'create')
  assert.equal(state.draft.value.title, 'Wzór AI')
  await state.save()
  assert.equal(calls[0][0], '/templates')
  assert.equal(calls[0][1], 'POST')
})
