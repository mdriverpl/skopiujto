import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, reactive } from 'vue'
import { resourceTasks } from './resourceTasks.js'

const compiled = compileScript(parse(readFileSync(new URL('./FolderTasks.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'folder-tasks-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(props) {
  const context = { computed, resourceTasks }
  runInNewContext(compiled, context)
  return context.component.setup(props, { expose() {}, emit() {} })
}
const task = (id, status = 'todo', extra = {}) => ({ key: `task:${id}`, origin: 'task', folder_id: 'folder-a',
  status, title: id, created_at: '2030-01-01T10:00:00Z', ...extra })

test('folder history combines mine and sent, removes self-assigned duplicates and retains completed tasks', () => {
  const own = task('self')
  const state = panel({ folder: { id: 'folder-a' }, taskData: {
    mine: [own, task('done', 'done'), task('cancelled', 'cancelled')],
    sent: [own, task('other-folder', 'todo', { folder_id: 'folder-b' }),
      task('file', 'todo', { folder_id: null, document_id: 'file-one' })] } })
  assert.equal(state.tasks.value.length, 3)
  assert.equal(state.waiting.value, 1)
  assert.equal(state.tasks.value[0].title, 'self')
  assert.ok(state.tasks.value.some(item => item.status === 'done'))
  assert.ok(state.tasks.value.some(item => item.status === 'cancelled'))
})

test('changing folders or receiving refreshed statuses updates the panel and pending count', () => {
  const props = reactive({ folder: { id: 'folder-a' }, taskData: {
    mine: [task('a'), task('b', 'in_progress', { folder_id: 'folder-b' })], sent: [] } })
  const state = panel(props)
  assert.equal(state.tasks.value[0].title, 'a')
  props.folder = { id: 'folder-b' }
  assert.equal(state.tasks.value[0].title, 'b')
  props.taskData.mine[1].status = 'done'
  assert.equal(state.waiting.value, 0)
  props.taskData.mine[1].folder_id = null
  assert.equal(state.tasks.value.length, 0)
})

test('file tab includes its assigned tasks, workflow, deadlines and approvals without unrelated resources', () => {
  const data = { mine: [task('assigned', 'todo', { document_id: 'file-a', folder_id: null }),
    { ...task('workflow'), origin: 'document', key: 'document:file-a', document_id: 'file-a' },
    { ...task('deadline', 'done'), origin: 'deadline', key: 'deadline:one', document_id: 'file-a' },
    task('hidden', 'todo', { document_id: null })],
    sent: [{ ...task('approval', 'accepted'), origin: 'approval', key: 'approval:one', document_id: 'file-a' },
      task('other-file', 'todo', { document_id: 'file-b' })] }
  const state = panel({ document: { id: 'file-a' }, taskData: data })
  assert.equal(state.tasks.value.length, 4)
  assert.equal(state.waiting.value, 2)
  assert.ok(state.tasks.value.some(item => item.origin === 'deadline'))
  assert.ok(state.tasks.value.some(item => item.status === 'accepted'))
  assert.equal(resourceTasks(data, { id: 'missing' }, 'file').length, 0)
  assert.equal(resourceTasks(data, null, 'file').length, 0)
})
