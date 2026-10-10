import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref, computed } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./SurveyAnswersAnalysis.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'analysis-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, surveys) {
  const context = { ref, computed, SurveyGrade: {} }
  runInNewContext(compiled, context)
  return context.component.setup({ api, surveys }, { expose() {}, emit() {} })
}
test('selection includes only owned surveys with submitted answers', () => {
  const state = panel(async () => {}, [{ id: 'own', is_owner: true, completed: 2 },
    { id: 'empty', is_owner: true, completed: 0 }, { id: 'foreign', is_owner: false, completed: 3 }])
  state.selectAll()
  assert.equal(state.selectedIds.value.join(','), 'own')
})
test('analysis sends selected surveys and displays the combined summary last', async () => {
  const calls = [], result = { surveys: [{ id: 'two', title: 'Druga' }, { id: 'one', title: 'Pierwsza' }], summary: { summary: 'Wspólne wnioski' } }
  const state = panel(async (...args) => { calls.push(args); return result }, [
    { id: 'one', is_owner: true, completed: 1 }, { id: 'two', is_owner: true, completed: 1 }])
  state.selectedIds.value = ['two', 'one']; state.prompt.value = '  Oceń obsługę  '
  await state.analyze()
  assert.equal(calls[0][0], '/surveys/interpretation')
  assert.equal(calls[0][2].survey_ids.join(','), 'two,one')
  assert.equal(calls[0][2].prompt, 'Oceń obsługę')
  assert.equal(state.sections.value[0].heading, '1. Druga')
  assert.equal(state.sections.value.at(-1).heading, 'Podsumowanie wszystkich ankiet')
})
test('duplicate requests are blocked and a failure preserves earlier results', async () => {
  let reject, calls = 0
  const state = panel(async () => { calls++; return new Promise((_, fail) => { reject = fail }) }, [{ id: 'one', is_owner: true, completed: 1 }])
  state.selectedIds.value = ['one']; state.prompt.value = 'Wskazówki'; state.report.value = { surveys: [], summary: { summary: 'Old' } }
  const pending = state.analyze(); await state.analyze()
  assert.equal(calls, 1)
  reject(Error('Błąd analizy')); await pending
  assert.equal(state.prompt.value, 'Wskazówki')
  assert.equal(state.report.value.summary.summary, 'Old')
  assert.equal(state.busy.value, false)
})

test('grading needs a prompt and is passed to the API when enabled', async () => {
  const calls = [], grade = { value: '4', scale: '1–5', criteria: 'Obsługa', justification: 'Dobra odpowiedź' }
  const state = panel(async (...args) => { calls.push(args); return { surveys: [{ id: 'one', title: 'Ocena', grade }], summary: { grade: null } } }, [{ id: 'one', is_owner: true, completed: 1 }])
  state.selectedIds.value = ['one']; state.grading.value = true
  await state.analyze(); assert.equal(calls.length, 0)
  state.prompt.value = 'Oceń obsługę w skali 1–5'
  await state.analyze()
  assert.equal(calls[0][2].grading, true)
  assert.equal(state.sections.value[0].grade.value, '4')
  assert.equal(state.sections.value.at(-1).grade, null)
})
