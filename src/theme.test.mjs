import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const source = readFileSync(new URL('./theme.js', import.meta.url), 'utf8').replace(/export /g, '')
function preference(stored, blocked = false) {
  const dataset = {}, writes = []
  const context = { document: { documentElement: { dataset }, querySelector: () => null }, localStorage: {
    getItem: () => { if (blocked) throw Error('Storage blocked'); return stored },
    setItem: (...args) => { if (blocked) throw Error('Storage blocked'); writes.push(args) },
  } }
  runInNewContext(source, context)
  return { ...context, dataset, writes }
}

test('theme preference survives reload and invalid saved preferences use normal', () => {
  assert.equal(preference('dark').savedTheme(), 'dark')
  assert.equal(preference('sweet').savedTheme(), 'sweet')
  assert.equal(preference('unknown').savedTheme(), 'normal')
  const state = preference(null)
  assert.equal(state.applyTheme('colorful'), 'colorful')
  assert.equal(state.dataset.theme, 'colorful')
  assert.deepEqual(state.writes, [['edokumenty-theme', 'colorful']])
})

test('blocked browser storage still allows switching themes', () => {
  const state = preference(null, true)
  assert.equal(state.savedTheme(), 'normal')
  assert.equal(state.applyTheme('dark'), 'dark')
  assert.equal(state.dataset.theme, 'dark')
  assert.equal(state.applyTheme('invalid'), 'normal')
})
