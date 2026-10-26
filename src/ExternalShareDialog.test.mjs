import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const source = compileScript(parse(readFileSync(new URL('./ExternalShareDialog.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'external-share-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function dialog(api) {
  const context = { computed, ref, URL, onMounted() {}, location: { origin: 'https://example.com' } }
  for (const icon of ['X', 'Link', 'Copy', 'Folder', 'Images', 'LayoutGrid', 'Eye', 'ShieldCheck']) context[icon] = {}
  runInNewContext(source, context)
  return context.component.setup({ api, resource: { id: 'root', kind: 'folder' } }, { expose() {}, emit() {} })
}

test('new links explicitly carry the chosen guest upload permission', async () => {
  const calls = []
  const state = dialog(async (path, method, body) => { calls.push({ path, method, body }); return method ? { id: 'link', path: '/public-share/token' } : [] })
  assert.equal(state.allowUploads.value, false)
  state.allowUploads.value = true; await state.create()
  assert.equal(calls[0].method, 'POST'); assert.equal(calls[0].body.allow_uploads, true)
  assert.equal(calls[0].body.hours, 168)
})

test('changing contribution permission preserves link display mode and restores failed changes', async () => {
  const calls = []; let allowed = true, fail = false
  const state = dialog(async (path, method, body) => {
    calls.push({ path, method, body })
    if (method) { if (fail) throw new Error('Denied'); allowed = body.allow_uploads; return {} }
    return [{ id: 'link', allow_uploads: allowed, view_mode: 'gallery' }]
  })
  await state.load(); const event = { target: { checked: false } }
  await state.changeUploads({ id: 'link' }, event)
  const change = calls.find(item => item.method === 'PATCH')
  assert.equal(change.body.allow_uploads, false); assert.equal(change.body.view_mode, undefined)
  fail = true; event.target.checked = true; await state.changeUploads({ id: 'link' }, event)
  assert.equal(event.target.checked, false); assert.equal(state.error.value, 'Denied')
})
