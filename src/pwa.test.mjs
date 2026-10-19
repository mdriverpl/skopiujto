import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const source = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
function worker(clients = []) {
  const listeners = {}, notifications = [], opened = [], cached = []
  const context = {
    URL,
    self: {
      location: { origin: 'https://documents.example' },
      addEventListener: (event, fn) => { listeners[event] = fn },
      skipWaiting: async () => {},
      clients: { claim: async () => {}, matchAll: async () => clients, openWindow: async url => { opened.push(url) } },
      registration: { showNotification: async (title, options) => { notifications.push({ title, ...options }) } }
    },
    caches: { open: async () => ({ addAll: async urls => { cached.push(...urls) } }), keys: async () => [], match: async () => 'offline' },
    fetch: async () => { throw Error('offline') }
  }
  runInNewContext(source, context)
  return { listeners, notifications, opened, cached }
}
test('push payload displays a notification and constrains destinations', async () => {
  const state = worker()
  let pending
  state.listeners.push({ data: { json: () => ({ title: 'New task', url: 'https://evil.example/' }) }, waitUntil: promise => { pending = promise } })
  await pending
  assert.equal(state.notifications[0].title, 'New task')
  assert.equal(state.notifications[0].data.url, 'https://documents.example/')
})
test('click focuses and navigates an existing window', async () => {
  const actions = []
  const state = worker([{ url: 'https://documents.example/', navigate: async url => actions.push(url), focus: async () => actions.push('focus') }])
  let pending
  state.listeners.notificationclick({ notification: { close() {}, data: { url: '/?section=tasks' } }, waitUntil: promise => { pending = promise } })
  await pending
  assert.deepEqual(actions, ['https://documents.example/?section=tasks', 'focus'])
  assert.equal(state.opened.length, 0)
})
test('navigation falls back offline and never intercepts API', async () => {
  const state = worker()
  let response
  state.listeners.fetch({ request: { method: 'GET', url: 'https://documents.example/api/documents', mode: 'navigate' }, respondWith() { throw Error('API intercepted') } })
  state.listeners.fetch({ request: { method: 'GET', url: 'https://documents.example/', mode: 'navigate' }, respondWith: promise => { response = promise } })
  assert.equal(await response, 'offline')
  let pending
  state.listeners.install({ waitUntil: promise => { pending = promise } })
  await pending
  assert.equal(state.cached.includes('/'), false)
  assert.equal(state.cached.includes('/offline.html'), true)
})
test('manifest has real install icons for Android and Windows', () => {
  const manifest = JSON.parse(readFileSync(new URL('../public/manifest.webmanifest', import.meta.url), 'utf8'))
  for (const size of ['192x192', '512x512']) {
    const icon = manifest.icons.find(icon => icon.sizes === size && icon.purpose === 'any')
    assert.ok(icon)
    const bytes = readFileSync(new URL('../public' + icon.src, import.meta.url))
    assert.equal(bytes.readUInt32BE(16), Number(size.split('x')[0]))
    assert.equal(bytes.readUInt32BE(20), Number(size.split('x')[1]))
  }
  assert.equal(manifest.display, 'standalone')
})
