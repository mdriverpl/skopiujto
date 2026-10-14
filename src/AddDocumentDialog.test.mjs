import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./AddDocumentDialog.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'add-document-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function dialog(templates = []) {
  const events = [], context = { computed, ref, AiPrompt: {} }
  runInNewContext(compiled, context)
  const state = context.component.setup({ templates, folderId: 'documents-root', folderName: 'Dokumenty' },
    { expose() {}, emit: (...args) => events.push(args) })
  return { state, events }
}

test('upload requests the existing file picker without creating an empty document', () => {
  const { state, events } = dialog()
  state.upload()
  assert.deepEqual(events, [['upload']])
  state.generating.value = true
  state.upload()
  assert.equal(events.length, 1)
})

test('blank and template documents remain unsaved drafts for the shared editor', () => {
  const template = { id: 'contract', title: 'Umowa', category: 'Umowy', content: 'Warunki', rich_content: null }
  const { state, events } = dialog([template])
  state.proceed()
  assert.equal(events[0][0], 'choose')
  assert.equal(events[0][1].status, 'Szkic')
  assert.equal(events[0][1].content, '')
  state.source.value = 'template'
  state.proceed()
  assert.equal(events.length, 1)
  state.templateId.value = template.id
  state.proceed()
  assert.equal(events[1][1].title, template.title)
  assert.equal(events[1][1].content, template.content)
})
