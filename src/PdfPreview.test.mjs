import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch, reactive } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./PdfPreview.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'pdf-preview-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function preview(fetcher) {
  const revoked = [], destroyed = [], calls = []
  const context = { computed, ref, watch, onMounted() {}, onBeforeUnmount(fn) { destroyed.push(fn) }, AbortController,
    URL: { createObjectURL() { return 'blob:pdf-preview' }, revokeObjectURL(url) { revoked.push(url) } },
    fetch(...args) { calls.push(args); return fetcher(...args) } }
  runInNewContext(compiled, context)
  const state = context.component.setup(reactive({ file: { id: 'pdf one', filename: 'test.pdf', version: 3 }, accountId: 'account' }), { expose() {}, emit() {} })
  return { state, calls, revoked, destroy() { for (const fn of destroyed) fn() } }
}

test('PDF preview uses account permissions and releases downloaded content on close', async () => {
  const item = preview(async () => ({ ok: true, headers: { get: () => 'application/pdf' }, blob: async () => ({}) }))
  await item.state.load()
  assert.match(item.calls.at(-1)[0], /pdf%20one\/preview\?v=3$/)
  assert.equal(item.calls.at(-1)[1].headers['X-Account-ID'], 'account')
  assert.equal(item.calls.at(-1)[1].credentials, 'same-origin')
  assert.equal(item.state.source.value, 'blob:pdf-preview')
  assert.equal(item.state.loading.value, false)
  item.destroy()
  assert.deepEqual(item.revoked, ['blob:pdf-preview'])
})

test('PDF access errors show the server message and do not create a preview', async () => {
  const item = preview(async () => ({ ok: false, json: async () => ({ detail: 'Brak dostępu.' }) }))
  await item.state.load()
  assert.equal(item.state.error.value, 'Brak dostępu.')
  assert.equal(item.state.source.value, '')
  item.destroy()
})

test('non-PDF response cannot be embedded as a PDF', async () => {
  const item = preview(async () => ({ ok: true, headers: { get: () => 'text/html' } }))
  await item.state.load()
  assert.match(item.state.error.value, /PDF/)
  assert.equal(item.state.source.value, '')
  item.destroy()
})
