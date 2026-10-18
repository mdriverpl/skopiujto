import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch } from 'vue'
import { helpTopics, getHelpTopic, findHelpTopics } from './helpContent.js'
import { defaultMenuOrder } from './menuOrder.js'

const compiled = compileScript(parse(readFileSync(new URL('./HelpPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'help-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(initialTopic = 'help', role = 'user') {
  const context = { computed, ref, watch, findHelpTopics }
  runInNewContext(compiled, context)
  return context.component.setup({ initialTopic, user: { role } }, { expose() {}, emit() {} })
}

test('contextual help opens requested module and search finds its detailed instructions', () => {
  const state = panel('edelivery')
  assert.equal(state.topic.value.id, 'edelivery')
  state.search.value = 'CSR'
  assert.equal(state.topic.value.id, 'edelivery')
  assert.equal(state.topics.value.length, 1)
  state.search.value = 'nieistniejacy temat 98765'
  assert.equal(state.topic.value, undefined)
  assert.equal(state.topics.value.length, 0)
  state.search.value = ''
  assert.equal(state.topic.value.id, 'edelivery')
})

test('administration guides are limited to administrators, including direct selection', () => {
  const user = panel('mail-key')
  assert.equal(user.topics.value.some(topic => topic.adminOnly), false)
  assert.equal(user.topic.value.id, 'help')
  user.search.value = 'generowanie klucza'
  assert.equal(user.topics.value.length, 0)
  const admin = panel('mail-key', 'admin')
  assert.equal(admin.topic.value.id, 'mail-key')
  admin.search.value = 'generowanie klucza'
  assert.equal(admin.topic.value.id, 'mail-key')
})

test('every navigable module has contextual guidance and unknown module falls back safely', () => {
  // Expandable menu groups have no page of their own; their child pages do.
  const pages = [...defaultMenuOrder.filter(id => !['planning', 'settings'].includes(id)),
    'tasks', 'calendar', 'notes', 'surveys', 'templates', 'admin', 'edelivery', 'active']
  for (const id of pages) {
    const topic = getHelpTopic(id)
    assert.equal(topic.id, id)
    assert.ok(topic.description && topic.steps.length > 0)
  }
  assert.equal(new Set(helpTopics.map(topic => topic.id)).size, helpTopics.length)
  assert.equal(getHelpTopic('unknown').id, 'help')
})
