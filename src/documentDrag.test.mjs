import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref } from 'vue'

const source = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const handlers = source.slice(source.indexOf('const draggedFile ='), source.indexOf('async function downloadPdf('))
function drive(fail = false) {
  const calls = [], context = { ref, busy: ref(false), rootRights: ref({ add: true }),
    folders: ref([{ id: 'target', permissions: { add: true } }, { id: 'readonly', permissions: { add: false } }]),
    api: async (...args) => { calls.push(args); if (fail) throw new Error('Brak dostępu') },
    run: action => action(), loadDocuments: async () => { calls.push(['reload']) } }
  runInNewContext(handlers + '\nglobalThis.state = { startFileDrag, endFileDrag, canDropFile, dragOverFolder, dropFile, draggedFile, dropFolder }', context)
  const event = { prevented: false, preventDefault() { this.prevented = true }, dataTransfer: { setData() {} } }
  return { ...context, ...context.state, calls, event }
}
const file = { id: 'doc', folder_id: 'source', version: 4, permissions: { move: true } }

test('drag allows writable folders and parent root, blocks source, readonly targets and busy state', () => {
  const state = drive()
  state.startFileDrag(state.event, file)
  assert.equal(state.canDropFile('target'), true)
  assert.equal(state.canDropFile(null), true)
  assert.equal(state.canDropFile('source'), false)
  assert.equal(state.canDropFile('readonly'), false)
  state.dragOverFolder(state.event, 'target')
  assert.equal(state.event.prevented, true)
  assert.equal(state.dropFolder.value, 'target')
  state.busy.value = true
  assert.equal(state.canDropFile('target'), false)
})

test('drop persists the location and reloads the list; server rejection also reloads and clears drag state', async () => {
  for (const fail of [false, true]) {
    const state = drive(fail)
    state.startFileDrag(state.event, file)
    const result = state.dropFile(state.event, 'target')
    if (fail) await assert.rejects(result, /Brak dostępu/)
    else await result
    assert.equal(state.calls[0][0], '/documents/doc/move')
    assert.equal(state.calls[0][1], 'PATCH')
    assert.equal(state.calls[0][2].folder_id, 'target')
    assert.equal(state.calls[0][2].version, 4)
    assert.equal(state.calls.at(-1)[0], 'reload')
    assert.equal(state.draggedFile.value, null)
    assert.equal(state.dropFolder.value, undefined)
  }
})

test('a file without move permission cannot start dragging', () => {
  const state = drive()
  state.startFileDrag(state.event, { ...file, permissions: { move: false } })
  assert.equal(state.event.prevented, true)
  assert.equal(state.draggedFile.value, null)
})
