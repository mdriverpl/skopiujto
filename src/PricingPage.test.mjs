import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import * as pricing from './pricing.js'

const compiled = compileScript(parse(readFileSync(new URL('./PricingPage.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'pricing-page-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function dialog(overrides = {}) {
  const context = { ...pricing, money: pricing.formatMoney, PricingNetwork: {}, computed, ref, onMounted() {}, onBeforeUnmount() {}, ...overrides }
  runInNewContext(compiled, context)
  return context.component.setup({}, { expose() {}, emit() {} })
}

test('NIS2 preset starts enabled and reflects manual changes to each required setting', () => {
  const state = dialog()
  assert.equal(state.nis2Preset.value, true)
  assert.equal(state.pricing.value.server.count, 2)
  assert.equal(state.pricing.value.database.ha, true)
  for (const id of ['ha', 'logs', 'waf']) {
    state.selected.value = state.selected.value.filter(option => option !== id)
    assert.equal(state.nis2Preset.value, false)
    state.nis2Preset.value = true
    assert.equal(state.nis2Preset.value, true)
  }
  state.databasePlan.value = 'none'
  assert.equal(state.nis2Preset.value, false)
  state.nis2Preset.value = true
  assert.equal(state.databasePlan.value, 'S1')
  assert.equal(state.pricing.value.database.ha, true)
})

test('offer button downloads PDF for current configuration without sending a client price', async () => {
  let sent, downloads = 0
  const link = { click() { downloads++ }, remove() {} }
  const state = dialog({
    fetch: async (path, options) => {
      sent = { path, body: JSON.parse(options.body) }
      return { ok: true, headers: { get: () => 'application/pdf' }, blob: async () => ({}) }
    },
    URL: { createObjectURL: () => 'blob:offer', revokeObjectURL() {} },
    document: { createElement: () => link, body: { append() {} } }, setTimeout() {},
  })
  state.form.value = { reportValidity: () => true }
  state.users.value = 42
  state.serverPlan.value = 'S8'
  await state.prepareOffer()
  assert.equal(sent.path, '/api/pricing/offer')
  assert.equal(sent.body.users, 42)
  assert.equal(sent.body.server_plan, 'S8')
  assert.equal(sent.body.database_ha, true)
  assert.equal('total' in sent.body, false)
  assert.equal(link.download, 'SpaceFlow-oferta.pdf')
  assert.equal(downloads, 1)
  assert.equal(state.preparing.value, false)
})

test('offer generation failure is visible and releases the button for retry', async () => {
  const state = dialog({ fetch: async () => { throw Error('Offline') } })
  state.form.value = { reportValidity: () => true }
  await state.prepareOffer()
  assert.match(state.status.value, /Nie udało się przygotować PDF/)
  assert.equal(state.preparing.value, false)
})

test('preset toggles required features while preserving chosen plans and S3 backup', () => {
  const state = dialog()
  state.serverPlan.value = 'S4'
  state.databasePlan.value = 'S8'
  state.nis2Preset.value = false
  assert.equal(state.pricing.value.server.count, 1)
  assert.equal(state.pricing.value.database.ha, false)
  assert.deepEqual([...state.selected.value], ['backup'])
  state.nis2Preset.value = true
  assert.equal(state.serverPlan.value, 'S4')
  assert.equal(state.databasePlan.value, 'S8')
  assert.equal(state.pricing.value.server.count, 2)
  assert.equal(state.pricing.value.database.ha, true)
  assert.ok(state.selected.value.includes('backup'))
  assert.equal(state.selected.value.length, 4)
})
