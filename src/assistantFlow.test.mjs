import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdtemp, unlink, rmdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'

const source = await readFile(new URL('./StartPanel.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'assistant-test' }).content
  .replace(/from (['"])([^'"]+)\1/g, (_, quote, specifier) => 'from ' + JSON.stringify(import.meta.resolve(specifier)))
const testDirectory = await mkdtemp(join(tmpdir(), 'edzio-test-'))
const compiledUrl = pathToFileURL(join(testDirectory, 'StartPanel.mjs'))
after(async () => { await unlink(compiledUrl); await rmdir(testDirectory) })
await writeFile(compiledUrl, compiled)
const { default: Component } = await import(compiledUrl.href)

async function form(plan, generation) {
  let state
  const calls = [], events = []
  let closes = 0
  const api = async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/ai/assistant/plan') return plan
    if (path === '/ai/generate') {
      if (generation instanceof Error) throw generation
      return generation
    }
    if (path === '/tasks') return { id: 'new-task' }
    throw new Error('Unexpected request: ' + path)
  }
  const props = { api, surveys: [], taskData: { mine: [] }, busy: false }
  await renderToString(createSSRApp({
    setup() {
      state = Component.setup(props, { expose() {}, emit: (...args) => events.push(args) })
      return () => null
    },
  }))
  state.commandDialog.value = { close() { closes++ }, showModal() {} }
  state.command.value = plan.prompt
  return { state, calls, events, closes: () => closes }
}

test('meeting stays a preview until confirmed, then opens the calendar', async () => {
  const plan = { action: 'meeting', title: 'Spotkanie', description: 'Sala 4', assignee_id: 'me',
    due_at: '2030-01-02T08:00:00Z', prompt: 'Zaplanuj spotkanie jutro o 9', explanation: 'Sprawdź termin.' }
  const f = await form(plan)
  await f.state.submitCommand()
  assert.deepEqual(f.calls.map(c => c.path), ['/ai/assistant/plan'])
  assert.equal(f.events.length, 0)
  assert.equal(f.state.assistantPlan.value.title, 'Spotkanie')
  await f.state.scheduleTask()
  assert.equal(f.calls[1].path, '/tasks')
  assert.equal(f.calls[1].body.assignee_id, 'me')
  assert.equal(f.calls[1].body.due_at, '2030-01-02T08:00:00.000Z')
  assert.deepEqual(f.events, [['scheduled']])
  assert.equal(f.closes(), 1)
})
test('meeting without a date cannot be written', async () => {
  const f = await form({ action: 'meeting', title: 'Spotkanie', description: '', assignee_id: 'me', due_at: null, prompt: 'Zaplanuj spotkanie' })
  await f.state.submitCommand()
  await f.state.scheduleTask()
  assert.equal(f.calls.length, 1)
  assert.match(f.state.assistantError.value, /datę i godzinę/)
  assert.equal(f.events.length, 0)
})
test('offer is generated as an unsaved document and goes to the editor', async () => {
  const draft = { title: 'Oferta', status: 'Szkic', content: 'Oferta dla pracowników' }
  const f = await form({ action: 'document', prompt: 'Zrób dokument oferta dla pracowników' }, draft)
  await f.state.submitCommand()
  assert.deepEqual(f.calls.map(c => c.path), ['/ai/assistant/plan', '/ai/generate'])
  assert.equal(f.calls[1].body.kind, 'document')
  assert.equal(f.calls[1].body.folder_id, null)
  assert.deepEqual(f.events, [['document', draft]])
})
test('message is forwarded for review without sending', async () => {
  const f = await form({ action: 'message', prompt: 'Wyślij wiadomość do zespołu' })
  await f.state.submitCommand()
  assert.deepEqual(f.calls.map(c => c.path), ['/ai/assistant/plan'])
  assert.deepEqual(f.events, [['command', 'Wyślij wiadomość do zespołu']])
})

test('note is prepared without writing and opens a reviewable note draft', async () => {
  const f = await form({ action: 'note', title: 'Ustalenia', description: 'Wysyłamy ofertę w piątek.', prompt: 'Zanotuj ustalenia' })
  await f.state.submitCommand()
  assert.deepEqual(f.calls.map(c => c.path), ['/ai/assistant/plan'])
  assert.deepEqual(f.events, [['note', { title: 'Ustalenia', content: 'Wysyłamy ofertę w piątek.' }]])
  assert.equal(f.closes(), 1)
})
test('clarification and generation failures stay in the dialog', async () => {
  const clarify = await form({ action: 'clarify', prompt: 'Zrób coś', explanation: 'Co mam przygotować?' })
  await clarify.state.submitCommand()
  assert.equal(clarify.closes(), 0)
  assert.equal(clarify.state.assistantReply.value, 'Co mam przygotować?')
  const denied = await form({ action: 'document', prompt: 'Zrób dokument' }, new Error('Brak uprawnień'))
  await denied.state.submitCommand()
  assert.equal(denied.closes(), 0)
  assert.equal(denied.state.assistantError.value, 'Brak uprawnień')
  assert.equal(denied.state.assistantBusy.value, false)
  assert.equal(denied.events.length, 0)
})
test('each dialog opening clears the previous command, preview and all errors', async () => {
  const f = await form({ action: 'meeting', prompt: 'Poprzednie spotkanie' })
  f.state.assistantPlan.value = { title: 'Stary podgląd' }
  f.state.voiceError.value = 'Stary błąd mikrofonu'
  f.state.assistantError.value = 'Method Not Allowed'
  f.state.assistantReply.value = 'Stara odpowiedź'
  f.state.listening.value = true
  f.state.openCommand()
  assert.equal(f.state.command.value, '')
  assert.equal(f.state.voiceError.value, '')
  assert.equal(f.state.assistantError.value, '')
  assert.equal(f.state.assistantReply.value, '')
  assert.equal(f.state.assistantPlan.value, null)
  assert.equal(f.state.listening.value, false)
  assert.equal(f.calls.length, 0)
})
test('reset disconnects old microphone callbacks and aborts recognition', async () => {
  let recorder
  globalThis.window = { SpeechRecognition: class {
    constructor() { recorder = this; this.aborted = false }
    start() { this.onstart?.() }
    abort() { this.aborted = true }
  } }
  try {
    const f = await form({ action: 'meeting', prompt: 'Stare polecenie' })
    f.state.dictate()
    assert.equal(f.state.listening.value, true)
    f.state.openCommand()
    assert.equal(recorder.aborted, true)
    assert.equal(recorder.onresult, null)
    assert.equal(recorder.onerror, null)
    assert.equal(recorder.onend, null)
    assert.equal(f.state.listening.value, false)
    assert.equal(f.state.command.value, '')
  } finally { delete globalThis.window }
})
test('survey command generates an unsaved survey draft and opens the survey form', async () => {
  const draft = { title: 'Satysfakcja pracowników', description: 'Krótka ankieta',
    questions: [{ id: 'q1', label: 'Jak oceniasz pracę?', type: 'select', required: true, options: ['Dobrze', 'Bardzo dobrze'] }] }
  const f = await form({ action: 'survey', prompt: 'Zrób ankietę dla naszych pracowników' }, draft)
  await f.state.submitCommand()
  assert.deepEqual(f.calls.map(c => c.path), ['/ai/assistant/plan', '/ai/generate'])
  assert.equal(f.calls[1].body.kind, 'survey')
  assert.deepEqual(f.events, [['survey-draft', draft]])
  assert.equal(f.closes(), 1)
})
