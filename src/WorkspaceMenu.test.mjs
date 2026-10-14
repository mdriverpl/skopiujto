import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { parse, compileScript } from '@vue/compiler-sfc'
import { computed, ref, watch } from 'vue'
import { defaultMenuOrder, normalizeMenuOrder, moveMenuItem } from './menuOrder.js'

const compiled = compileScript(parse(readFileSync(new URL('./WorkspaceMenu.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'menu-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function menu(storage = new Map(), user = { id: 'me', role: 'user' }, api) {
  const events = [], captures = new Set(), calls = []
  const context = { computed, ref, watch, onBeforeUnmount() {}, defaultMenuOrder, normalizeMenuOrder, moveMenuItem,
    localStorage: { getItem: key => storage.get(key) || null, removeItem: key => storage.delete(key) } }
  for (const icon of ['House', 'Mail', 'ClipboardList', 'CalendarDays', 'StickyNote', 'Files', 'ClipboardCheck', 'HardDrive', 'FileText', 'BookOpen', 'Users', 'X']) context[icon] = {}
  runInNewContext(compiled, context)
  const save = async (path, method, body) => {
    calls.push({ path, method, body })
    return api ? await api(path, method, body) : { menu_order: body.menu_order }
  }
  const state = context.component.setup({ user, api: save, view: 'notes', open: true, tasksWaiting: 3, activeSurveys: 2 },
    { expose() {}, emit: (...args) => events.push(args) })
  state.menu.value = {
    getBoundingClientRect: () => ({ left: 0, right: 230, top: 0, bottom: 500 }),
    setPointerCapture: id => captures.add(id), hasPointerCapture: id => captures.has(id), releasePointerCapture: id => captures.delete(id),
    querySelectorAll: () => state.items.value.map((item, index) => ({ dataset: { menuId: item.id },
      getBoundingClientRect: () => ({ top: index * 40, bottom: index * 40 + 40, height: 40 }) }))
  }
  return { state, events, storage, captures, calls }
}
const settle = () => new Promise(resolve => setImmediate(resolve))
const pointer = (fields = {}) => ({ ctrlKey: true, button: 0, pointerType: 'mouse', pointerId: 1, clientX: 10, clientY: 10, preventDefault() {}, ...fields })

test('stored order ignores invalid and duplicate entries and includes new menu items', () => {
  assert.deepEqual(normalizeMenuOrder(['notes', 'notes', 'unknown', 'start']).slice(0, 3), ['notes', 'start', 'ai'])
  assert.equal(normalizeMenuOrder({}).length, defaultMenuOrder.length)
  const { state } = menu(new Map([['edokumenty-menu-order:me', JSON.stringify(['notes', 'start'])]]))
  assert.equal(state.items.value[0].id, 'notes')
  assert.equal(state.items.value.some(item => item.id === 'admin'), false)
  assert.equal(state.active('notes'), true)
  assert.equal(state.active('start'), false)
})

test('Ctrl dragging writes the account API and prevents navigation', async () => {
  const { state, calls, events, captures } = menu()
  state.pointerDown('start', pointer())
  state.pointerMove(pointer({ clientY: 185 }))
  assert.equal(state.dragged.value, 'start')
  assert.equal(state.order.value[4], 'start')
  assert.equal(calls.length, 0)
  state.pointerUp(pointer({ clientY: 185 }))
  assert.equal(captures.size, 0)
  assert.equal(state.dragged.value, null)
  assert.equal(calls[0].path, '/me/menu-order')
  assert.equal(calls[0].method, 'PUT')
  assert.equal(calls[0].body.menu_order[4], 'start')
  state.select('start', { ctrlKey: false })
  assert.equal(events.length, 0)
  await settle()
  assert.equal(events[0][0], 'order-saved')
  assert.equal(menu(new Map(), { id: 'me', role: 'user', menu_order: calls[0].body.menu_order }).state.items.value[4].id, 'start')
  assert.equal(menu(new Map(), { id: 'other', role: 'user' }).state.items.value[0].id, 'start')
})

test('ordinary mouse gestures still navigate and do not reorder', () => {
  const { state, events, storage } = menu()
  state.pointerDown('notes', pointer({ ctrlKey: false }))
  state.pointerMove(pointer({ clientY: 300, ctrlKey: false }))
  state.pointerUp(pointer({ ctrlKey: false }))
  state.select('notes', { ctrlKey: false })
  assert.deepEqual(events, [['navigate', 'notes'], ['close']])
  assert.equal(storage.size, 0)
})

test('cancelled drag or dropping outside the menu restores the original order', () => {
  const { state, storage } = menu()
  state.pointerDown('start', pointer())
  state.pointerMove(pointer({ clientY: 185 }))
  state.cancelDrag()
  assert.deepEqual(Array.from(state.order.value), defaultMenuOrder)
  state.pointerDown('start', pointer())
  state.pointerMove(pointer({ clientY: 185 }))
  state.pointerUp(pointer({ clientX: 500, clientY: 185 }))
  assert.deepEqual(Array.from(state.order.value), defaultMenuOrder)
  assert.equal(storage.size, 0)
})

test('Ctrl arrows reorder the focused item and keep administrator items available', async () => {
  const { state, calls } = menu(new Map(), { id: 'admin-user', role: 'admin' })
  assert.equal(state.items.value.at(-1).id, 'admin')
  state.keyMove('notes', { ctrlKey: true, key: 'ArrowUp', preventDefault() {} })
  assert.equal(state.items.value[defaultMenuOrder.indexOf('notes') - 1].id, 'notes')
  assert.equal(calls.length, 1)
  await settle()
  state.keyMove('notes', { ctrlKey: true, key: 'ArrowDown', preventDefault() {} })
  assert.equal(state.items.value[defaultMenuOrder.indexOf('notes')].id, 'notes')
})

test('existing browser preference is migrated once and database order takes precedence', async () => {
  const storage = new Map([['edokumenty-menu-order:me', JSON.stringify(['notes', 'start'])]])
  const { state, calls } = menu(storage)
  assert.equal(state.order.value[0], 'notes')
  assert.equal(calls.length, 1)
  await settle()
  assert.equal(storage.size, 0)
  const database = menu(new Map([['edokumenty-menu-order:me', JSON.stringify(['notes'])]]),
    { id: 'me', role: 'user', menu_order: ['documents', 'start'] })
  assert.equal(database.state.order.value[0], 'documents')
  assert.equal(database.calls.length, 0)
})

test('failed save keeps the chosen order for retry and does not report success', async () => {
  let fail = true
  const { state, events, calls } = menu(new Map(), { id: 'me', role: 'user' }, async (path, method, body) => {
    if (fail) throw new Error('Offline')
    return body
  })
  state.keyMove('notes', { ctrlKey: true, key: 'ArrowUp', preventDefault() {} })
  // A second reordering cannot race with the first save.
  state.keyMove('notes', { ctrlKey: true, key: 'ArrowUp', preventDefault() {} })
  assert.equal(calls.length, 1)
  await settle()
  assert.equal(state.order.value[defaultMenuOrder.indexOf('notes') - 1], 'notes')
  assert.match(state.saveError.value, /Nie udało/)
  assert.equal(state.announcement.value, '')
  assert.equal(events.length, 0)
  fail = false
  await state.saveOrder()
  assert.equal(state.saveError.value, '')
  assert.equal(events[0][0], 'order-saved')
})
