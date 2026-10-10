import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./AiPrompt.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'ai-prompt-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')

async function panel(api, kind = 'document', folderId = null) {
  const mounted = [], events = [], context = { ref, computed, FormData, onMounted: callback => mounted.push(callback) }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, kind, folderId }, { expose() {}, emit: (...args) => events.push(args) })
  await Promise.all(mounted.map(callback => callback()))
  return { state, events }
}

test('missing configuration blocks paid requests while preserving the prompt', async () => {
  const calls = []
  const { state, events } = await panel(async path => { calls.push(path); return { available: false, message: 'Brak klucza' } })
  state.prompt.value = 'Przygotuj dokument'
  await state.generate()
  assert.equal(calls.length, 1)
  assert.equal(state.prompt.value, 'Przygotuj dokument')
  assert.equal(state.error.value, 'Brak klucza')
  assert.equal(events.length, 0)
})

test('survey generation sends survey kind and delivers questions without saving', async () => {
  const calls = [], draft = { title: 'Ocena', description: '', questions: [{ id: 'q_1', label: 'Uwagi', type: 'textarea', required: false, options: [] }] }
  const { state, events } = await panel(async (...args) => {
    calls.push(args)
    return args[0] === '/ai/config' ? { available: true, message: '' } : draft
  }, 'survey')
  assert.equal(state.subject.value, 'ankietę')
  state.prompt.value = 'Ankieta satysfakcji'
  await state.generate()
  assert.equal(calls.length, 2)
  assert.equal(calls[1][0], '/ai/generate')
  assert.equal(calls[1][2].kind, 'survey')
  assert.equal(events.find(event => event[0] === 'generated')[1], draft)
})

test('generation passes the folder and delivers an unsaved draft to the editor', async () => {
  const calls = [], draft = { title: 'Dokument AI', content: 'Treść', rich_content: null }
  const { state, events } = await panel(async (...args) => {
    calls.push(args)
    return args[0] === '/ai/config' ? { available: true, message: '' } : draft
  }, 'document', 'selected-folder')
  state.prompt.value = 'Przygotuj dokument'
  await state.generate()
  assert.equal(calls.length, 2)
  assert.equal(calls[1][0], '/ai/generate')
  assert.equal(calls[1][1], 'POST')
  assert.equal(calls[1][2].folder_id, 'selected-folder')
  assert.equal(calls[1][2].kind, 'document')
  assert.equal(calls[1][2].prompt, 'Przygotuj dokument')
  assert.equal(events.find(event => event[0] === 'generated')[1], draft)
  assert.equal(state.busy.value, false)
})

test('provider failure preserves text, releases the busy state and allows retry', async () => {
  let fail = true
  const { state, events } = await panel(async path => {
    if (path === '/ai/config') return { available: true, message: '' }
    if (fail) throw new Error('Limit OpenAI')
    return { title: 'Szablon AI' }
  }, 'template')
  state.prompt.value = 'Przygotuj szablon'
  await state.generate()
  assert.equal(state.error.value, 'Limit OpenAI')
  assert.equal(state.prompt.value, 'Przygotuj szablon')
  assert.equal(state.busy.value, false)
  assert.equal(events.some(event => event[0] === 'generated'), false)
  fail = false
  await state.generate()
  assert.equal(state.error.value, '')
  assert.equal(events.some(event => event[0] === 'generated'), true)
})

test('repeated click during generation does not send a second request', async () => {
  let resolve, calls = 0
  const { state } = await panel(async path => {
    if (path === '/ai/config') return { available: true, message: '' }
    calls++
    return new Promise(done => { resolve = done })
  })
  state.prompt.value = 'Przygotuj dokument'
  const running = state.generate()
  await state.generate()
  assert.equal(calls, 1)
  resolve({ title: 'Dokument' })
  await running
  assert.equal(state.busy.value, false)
})

test('template can be generated from a file without a prompt using multipart upload', async () => {
  const calls = []
  const { state, events } = await panel(async (...args) => {
    calls.push(args)
    return args[0] === '/ai/config' ? { available: true, message: '' } : { title: 'Wzór z pliku' }
  }, 'template')
  const file = new File(['Contract'], 'contract.txt', { type: 'text/plain' })
  state.selectFile({ target: { files: [file] } })
  await state.generate()
  assert.equal(calls[1][0], '/ai/templates/from-file')
  assert.equal(calls[1][1], 'POST')
  assert.equal(calls[1][2] instanceof FormData, true)
  assert.equal(calls[1][2].get('file').name, 'contract.txt')
  assert.equal(calls[1][2].get('prompt'), '')
  assert.equal(events.find(event => event[0] === 'generated')[1].title, 'Wzór z pliku')
})

test('unsupported, empty and oversized sources are blocked before generation', async () => {
  const calls = []
  const { state } = await panel(async path => { calls.push(path); return { available: true, message: '' } }, 'template')
  for (const file of [{ name: 'bad.exe', size: 10 }, { name: 'blank.txt', size: 0 }, { name: 'large.pdf', size: 10 * 1024 * 1024 + 1 }]) {
    state.selectFile({ target: { files: [file], value: 'selected' } })
    assert.equal(state.sourceFile.value, null)
    assert.equal(!!state.error.value, true)
    await state.generate()
  }
  assert.equal(calls.length, 1)
})

test('removing a source restores prompt-only generation', async () => {
  const calls = []
  const { state } = await panel(async (...args) => {
    calls.push(args); return args[0] === '/ai/config' ? { available: true, message: '' } : { title: 'Wzór' }
  }, 'template')
  state.selectFile({ target: { files: [new File(['Contract'], 'contract.txt')] } })
  state.clearFile()
  state.prompt.value = 'Utwórz szablon'
  await state.generate()
  assert.equal(state.sourceFile.value, null)
  assert.equal(calls[1][0], '/ai/generate')
  assert.equal(calls[1][2].kind, 'template')
})

test('failed upload preserves source and prompt for another attempt', async () => {
  const { state, events } = await panel(async path => {
    if (path === '/ai/config') return { available: true, message: '' }
    throw new Error('Limit OpenAI')
  }, 'template')
  state.selectFile({ target: { files: [new File(['Contract'], 'contract.txt')] } })
  state.prompt.value = 'Zachowaj wszystkie postanowienia'
  await state.generate()
  assert.equal(state.error.value, 'Limit OpenAI')
  assert.equal(state.sourceFile.value.name, 'contract.txt')
  assert.equal(state.prompt.value, 'Zachowaj wszystkie postanowienia')
  assert.equal(state.busy.value, false)
  assert.equal(events.some(event => event[0] === 'generated'), false)
})
