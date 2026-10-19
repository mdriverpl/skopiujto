import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./FlowsPanel.vue', import.meta.url), 'utf8')).descriptor, { id: 'flows-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, currentUser = { id: 'me', role: 'admin' }) {
  const context = { computed, ref, watch, onMounted() {}, window: { confirm: () => true } }
  for (const icon of ['GitBranch', 'Plus', 'Search', 'RefreshCw', 'X', 'Save', 'Pencil', 'Trash2', 'ArrowDown', 'ArrowUp', 'Mail', 'FileText', 'ClipboardList', 'CheckCircle2', 'Bell', 'Folder', 'Play', 'ChevronRight']) context[icon] = {}
  runInNewContext(compiled, context)
  return context.component.setup({ api, currentUser }, { expose() {} })
}
test('invoice example uses existing company groups and saves an ordered draft', async () => {
  let request
  const state = panel(async (path, method, body) => { request = { path, method, body }; return { id: 'saved', ...body, status: 'draft' } })
  state.options.value.groups = [{ id: 'accounts', name: 'Rozliczenia' }, { id: 'finance', name: 'Finanse' }]
  state.open(); state.useInvoiceExample()
  assert.equal(state.draft.value.steps[0].target_id, 'accounts')
  assert.equal(state.draft.value.steps[1].target_id, 'finance')
  assert.equal(state.draft.value.trigger.event, 'email_received')
  await state.save()
  assert.equal(request.path, '/flows'); assert.equal(request.method, 'POST')
  assert.deepEqual(Array.from(request.body.steps, step => step.kind), ['approval', 'task'])
  assert.equal(request.body.steps[0].folder_id, null)
  assert.equal(state.draft.value, null); assert.equal(state.flows.value.length, 1)
})
test('step order is preserved and version conflicts keep unsaved changes', async () => {
  let body
  const state = panel(async (path, method, value) => { body = value; throw new Error('Version conflict') })
  state.open();state.draft.value.name = 'Process';state.addStep('approval')
  const first = state.draft.value.steps[0].id
  state.moveStep(0, 1);assert.equal(state.draft.value.steps[1].id, first)
  state.draft.value.id = 'existing';state.draft.value.version = 4
  await state.save()
  assert.equal(body.version, 4);assert.equal(body.steps[1].id, first)
  assert.equal(state.draft.value.name, 'Process');assert.equal(state.formError.value, 'Version conflict')
})
test('save rejects incomplete steps and read-only accounts cannot change flows', async () => {
  const calls = []
  const state = panel(async (...args) => calls.push(args))
  state.open();await state.save();assert.equal(calls.length, 0)
  state.draft.value.name = 'Process';state.draft.value.steps[0].target_id = '';await state.save();assert.equal(calls.length, 0)
  const reader = panel(async (...args) => calls.push(args), { id: 'me', role: 'user' })
  reader.open();reader.draft.value.name = 'Process';await reader.save();assert.equal(calls.length, 0)
  assert.equal(panel(async () => ({}), { id: 'me', role: 'admin', impersonation: {} }).canManage.value, false)
})
test('document step sends only the folder target', () => {
  const state = panel(async () => ({}));state.open();state.draft.value.name = 'Save files'
  const step = state.draft.value.steps[0];state.changeKind(step, 'save_document');step.folder_id = 'folder'
  const data = state.payload();assert.equal(data.steps[0].target_id, null);assert.equal(data.steps[0].folder_id, 'folder')
})
