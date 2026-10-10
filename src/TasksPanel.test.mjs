import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./TasksPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'tasks-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
const me = { id: 'me', name: 'Jan' }
const task = { id: 'one', key: 'task:one', origin: 'task', kind: 'general', title: 'Sprawdź umowę',
  status: 'todo', can_update: true, can_cancel: false, version: 1, sender_name: 'Anna' }
const approval = { id: 'approval', key: 'approval:approval', origin: 'approval', kind: 'approval', title: 'Umowa',
  status: 'waiting', can_accept: true, can_download: true, file_version: 2, filename: 'umowa.pdf' }
function panel(api, props = {}) {
  const mounted = [], events = [], context = { computed, ref, onMounted: callback => mounted.push(callback),
    onBeforeUnmount() {}, setInterval() { return 1 }, clearInterval() {}, window: { confirm: () => true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, currentUser: me, documents: [{ id: 'doc-one', title: 'Umowa' }],
    folders: [{ id: 'parent', name: 'Firma', permissions: { read: false } },
      { id: 'folder-one', parent_id: 'parent', name: 'Umowy', permissions: { read: true } }], ...props },
    { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, mount: () => mounted[0]() }
}

test('filters show tasks for me or sent tasks, with text and status filtering', async () => {
  const { state, events, mount } = panel(async () => ({ mine: [task, approval], sent: [{ ...task, id: 'sent', title: 'Wysłane' }], waiting: 2 }))
  mount(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.filtered.value.length, 2)
  state.search.value = 'anna'; assert.equal(state.filtered.value.length, 1)
  state.search.value = ''; state.scope.value = 'sent'
  assert.equal(state.filtered.value[0].title, 'Wysłane')
  state.statusFilter.value = 'done'; assert.equal(state.filtered.value.length, 0)
  assert.ok(events.some(event => event[0] === 'loaded' && event[1].waiting === 2))
})

test('new task is assigned with optional document and time and switches to sent filter', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/sharing-options') return { users: [{ id: 'anna', name: 'Anna' }] }
    return method ? task : { mine: [], sent: [task], waiting: 0 }
  })
  await state.newTask()
  assert.equal(state.users.value[0].id, me.id)
  state.draft.value.title = 'Podpisz umowę'; state.draft.value.kind = 'signature'; state.draft.value.assignee_id = 'anna'
  await state.create()
  assert.equal(calls[1].path, '/tasks')
  assert.equal(calls[1].method, 'POST')
  assert.equal(calls[1].body.kind, 'signature')
  assert.equal(calls[1].body.assignee_id, 'anna')
  assert.equal(calls[1].body.document_id, null)
  assert.equal(calls[1].body.folder_id, null)
  assert.equal(calls[1].body.due_at, null)
  assert.equal(state.draft.value, null)
  assert.equal(state.scope.value, 'sent')
})

test('resource choice sends only the selected folder or file and general clears both', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    if (method) calls.push(body)
    return path === '/sharing-options' ? { users: [] } : { mine: [], sent: [], waiting: 0 }
  })
  for (const choice of ['folder', 'file', 'general']) {
    await state.newTask()
    state.targetType.value = choice
    state.draft.value.title = 'Sprawdź'; state.draft.value.assignee_id = 'me'
    state.draft.value.folder_id = 'folder-one'; state.draft.value.document_id = 'doc-one'
    await state.create()
  }
  assert.equal(calls[0].folder_id, 'folder-one'); assert.equal(calls[0].document_id, null)
  assert.equal(calls[1].folder_id, null); assert.equal(calls[1].document_id, 'doc-one')
  assert.equal(calls[2].folder_id, null); assert.equal(calls[2].document_id, null)
})

test('resource selections are required; folders use their path and inaccessible folders cannot open', async () => {
  let posts = 0
  const { state, events } = panel(async (path, method) => {
    if (method) posts++
    return { users: [] }
  })
  await state.newTask(); state.targetType.value = 'folder'; await state.create()
  assert.equal(posts, 0); assert.match(state.formError.value, /katalog/)
  state.targetType.value = 'file'; await state.create()
  assert.equal(posts, 0); assert.match(state.formError.value, /plik/)
  assert.equal(state.folderLabel(state.availableFolders.value[0]), 'Firma / Umowy')
  state.openFolder({ folder_id: 'parent' }); assert.equal(events.length, 0)
  state.openFolder({ folder_id: 'folder-one' })
  assert.deepEqual(events[0], ['open-folder', 'folder-one'])
})

test('failed assignment preserves entered task and a retry does not change recipient', async () => {
  const { state } = panel(async (path, method) => {
    if (method) throw new Error('Odbiorca nie ma dostępu')
    return { users: [{ id: 'anna', name: 'Anna' }] }
  })
  await state.newTask()
  state.draft.value.title = 'Podpisz'; state.draft.value.assignee_id = 'anna'
  await state.create()
  assert.equal(state.formError.value, 'Odbiorca nie ma dostępu')
  assert.equal(state.draft.value.title, 'Podpisz')
  assert.equal(state.draft.value.assignee_id, 'anna')
  assert.equal(state.busy.value, false)
})

test('status transitions use task version and refuse actions without participant rights', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return method ? {} : { mine: [], sent: [], waiting: 0 }
  })
  await state.changeStatus({ ...task, can_update: false }, 'done')
  await state.changeStatus(task, 'cancelled')
  assert.equal(calls.length, 0)
  await state.changeStatus(task, 'done')
  assert.equal(calls[0].path, '/tasks/one/status')
  assert.equal(calls[0].method, 'PATCH')
  assert.equal(calls[0].body.version, 1)
  assert.equal(calls[0].body.status, 'done')
})

test('approval keeps explicit confirmation and uses existing recipient acceptance API', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return method ? {} : { mine: [], sent: [], waiting: 0 }
  })
  state.scope.value = 'sent'; state.openApproval(approval)
  assert.equal(state.selected.value, null)
  state.scope.value = 'mine'; state.openApproval(approval)
  await state.accept(); assert.equal(calls.length, 0)
  state.confirmed.value = true; await state.accept()
  assert.equal(calls[0].path, '/approval-inbox/approval/accept')
  assert.equal(calls[0].body.confirmed, true)
  assert.equal(state.selected.value, null)
})

test('document tasks open the editor while sent approval tasks open history', () => {
  const { state, events } = panel(async () => ({}))
  state.openDocument({ origin: 'document', document_id: 'doc-one' })
  state.openDocument({ origin: 'approval', document_id: 'doc-one' })
  state.openDocument({ origin: 'task', document_id: 'not-accessible' })
  assert.equal(events[0][0], 'open-document')
  assert.equal(events[1][0], 'open-email')
  assert.equal(events.length, 2)
})

test('deadline tasks finish through the document deadline API', async () => {
  const calls = []
  const { state } = panel(async (path, method, body) => {
    calls.push({ path, method, body }); return method ? {} : { mine: [], sent: [], waiting: 0 }
  })
  await state.changeStatus({ id: 'due-one', origin: 'deadline', document_id: 'doc-one', can_update: true }, 'done')
  assert.equal(calls[0].path, '/documents/doc-one/deadlines/due-one')
  assert.equal(calls[0].body.done, true)
})

test('drive shortcuts preselect the folder or file and close the dialog after assignment', async () => {
  for (const target of [{ folder_id: 'folder-one' }, { document_id: 'doc-one' }]) {
    const calls = []
    const { state, events, mount } = panel(async (path, method, body) => {
      calls.push({ path, method, body }); return { users: [] }
    }, { initialTarget: target, dialogOnly: true })
    mount(); await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.targetType.value, target.folder_id ? 'folder' : 'file')
    assert.equal(state.draft.value.folder_id, target.folder_id || '')
    assert.equal(state.draft.value.document_id, target.document_id || '')
    state.draft.value.title = 'Sprawdź'; state.draft.value.assignee_id = 'me'
    await state.create()
    assert.equal(calls.length, 2)
    assert.equal(calls[1].body.folder_id, target.folder_id || null)
    assert.equal(calls[1].body.document_id, target.document_id || null)
    assert.ok(events.some(event => event[0] === 'updated'))
    assert.ok(events.some(event => event[0] === 'close'))
  }
})

test('shortcut dialog can close or retry loading recipients and preserves failed assignment', async () => {
  let failLoading = true
  const { state, events } = panel(async (path, method) => {
    if (failLoading) throw new Error('Brak połączenia')
    if (method) throw new Error('Brak dostępu')
    return { users: [] }
  }, { initialTarget: { folder_id: 'folder-one' }, dialogOnly: true })
  await state.newTask(); assert.equal(state.error.value, 'Brak połączenia')
  assert.equal(state.draft.value, null)
  failLoading = false; await state.newTask()
  state.draft.value.title = 'Sprawdź'
  await state.create()
  assert.equal(state.draft.value.folder_id, 'folder-one')
  assert.equal(state.formError.value, 'Brak dostępu')
  assert.equal(events.length, 0)
  state.closeDraft(); assert.equal(state.draft.value, null)
  assert.equal(events[0][0], 'close')
})
