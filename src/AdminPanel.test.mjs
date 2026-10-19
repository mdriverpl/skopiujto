import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, onMounted, ref, watch } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./AdminPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'admin-company-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(superadmin = false, confirm = () => true, failure = false) {
  const calls = []
  const user = { id: 'admin', company_id: 'one', role: 'admin', is_superadmin: superadmin }
  const api = async (path, method, body) => {
    calls.push({ path, method, body })
    if (method === 'DELETE' && failure) throw new Error('Konto ma powiązane dane.')
    if (path === '/me/company') return { id: 'one', name: 'Firma' }
    if (path === '/admin/companies') return [{ id: 'one' }, { id: 'two' }]
    if (path === '/admin/groups' && !method) return [{ id: 'group', company_id: 'one', members: [], permissions: [] }]
    if (path.startsWith('/admin/users') && !method) return [{ id: 'a', company_id: 'one' }, { id: 'b', company_id: 'two' }]
    return []
  }
  const context = { computed, ref, watch, onMounted() {}, window: { confirm } }
  runInNewContext(compiled, context)
  return { state: context.component.setup({ api, currentUser: user }, { expose() {}, emit() {} }), calls }
}
test('company administrator loads own company and group members only', async () => {
  const { state, calls } = panel()
  await state.load()
  assert.equal(calls.some(call => call.path === '/admin/companies'), false)
  assert.equal(state.companies.value.length, 1)
  assert.equal(state.groupAccounts.value.length, 1)
  state.editAccount()
  assert.equal(state.accountForm.value.company_id, 'one')
})
test('superadministrator chooses company for new account', async () => {
  const { state, calls } = panel(true)
  await state.load()
  assert.equal(state.companies.value.length, 2)
  state.editAccount()
  state.accountForm.value.name = 'New user'
  state.accountForm.value.email = 'new@example.com'
  state.accountForm.value.company_id = 'two'
  await state.saveAccount()
  const created = calls.find(call => call.method === 'POST' && call.path === '/admin/users')
  assert.equal(created.body.company_id, 'two')
})

test('deletion requires confirmation and protects current account and superadmin', async () => {
  const { state, calls } = panel(true, () => false)
  await state.deleteAccount({ id: 'a', name: 'Alice' })
  assert.equal(calls.length, 0)
  const protectedPanel = panel(true)
  await protectedPanel.state.deleteAccount({ id: 'admin' })
  await protectedPanel.state.deleteAccount({ id: 'super', is_superadmin: true })
  assert.equal(protectedPanel.calls.length, 0)
})
test('confirmed deletion refreshes users and reports success', async () => {
  const { state, calls } = panel(true)
  await state.deleteAccount({ id: 'a', name: 'Alice' })
  assert.equal(calls[0].path, '/admin/users/a')
  assert.equal(calls[0].method, 'DELETE')
  assert.ok(calls.some(call => call.path === '/admin/users?include_deleted=true' && !call.method))
  assert.match(state.notice.value, /Dokumenty i historia zostały zachowane/)
})
test('blocked deletion displays error and keeps user list', async () => {
  const { state, calls } = panel(true, () => true, true)
  await state.load()
  const accounts = state.accounts.value
  calls.length = 0
  await state.deleteAccount({ id: 'a', name: 'Alice' })
  assert.equal(state.accounts.value, accounts)
  assert.equal(state.error.value, 'Konto ma powiązane dane.')
  assert.equal(state.notice.value, '')
  assert.equal(calls.length, 1)
})


test('archived accounts stay separate from active users and remain available for admin preview', async () => {
  const { state, calls } = panel()
  state.accounts.value = [{ id: 'active', company_id: 'one' }, { id: 'archived', company_id: 'one', active: false, deleted_at: '2026-10-19' }]
  assert.equal(state.activeAccounts.value.length, 1)
  assert.equal(state.visibleAccounts.value[0].id, 'active')
  state.showDeleted.value = true
  assert.equal(state.visibleAccounts.value[0].id, 'archived')
  await state.enterAccount(state.visibleAccounts.value[0])
  assert.ok(calls.some(call => call.path === '/admin/users/archived/impersonate' && call.method === 'POST'))
})
