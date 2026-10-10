import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./SurveyPublic.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'survey-public-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { ref, onMounted() {} }
  runInNewContext(compiled, context)
  return context.component.setup({ api, token: 'private-token' }, { expose() {} })
}
test('public form needs only the invitation token and records one submission', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    return method ? { submitted_at: '2030-01-01' } : { title: 'Survey', questions: [{ id: 'name', type: 'text' }, { id: 'yes', type: 'checkbox' }] }
  })
  await state.load()
  assert.equal(state.answers.value.yes, false)
  state.answers.value.name = 'Anna'; await state.submit(); await state.submit()
  assert.equal(calls.length, 2); assert.equal(calls[1].path, '/survey-links/private-token/responses')
  assert.equal(calls[1].body.answers.name, 'Anna')
})
test('expired or closed invitations do not submit and server errors preserve typed answers', async () => {
  const state = panel(async () => { throw Error('Link wygasł') })
  await state.load(); assert.equal(state.error.value, 'Link wygasł')
  state.survey.value = { closed_at: '2030-01-01' }; await state.submit()
  state.survey.value = {}; state.answers.value = { name: 'Anna' }; await state.submit()
  assert.equal(state.answers.value.name, 'Anna'); assert.equal(state.busy.value, false)
})
