import test from 'node:test'
import assert from 'node:assert/strict'
import { readStartLayout, saveStartLayout } from './startLayout.js'

test('new layout defaults to v2 and each account keeps its own choice', () => {
  const stored = new Map()
  globalThis.localStorage = { getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value) }
  try {
    assert.equal(readStartLayout('anna'), 'v2')
    saveStartLayout('anna', 'v1')
    assert.equal(readStartLayout('anna'), 'v1')
    assert.equal(readStartLayout('jan'), 'v2')
    saveStartLayout('anna', 'invalid')
    assert.equal(readStartLayout('anna'), 'v1')
    saveStartLayout('anna', 'v2')
    assert.equal(readStartLayout('anna'), 'v2')
  } finally { delete globalThis.localStorage }
})

test('layout remains usable when browser storage is unavailable', () => {
  globalThis.localStorage = { getItem() { throw new Error('Unavailable') }, setItem() { throw new Error('Unavailable') } }
  try {
    assert.equal(readStartLayout('anna'), 'v2')
    assert.doesNotThrow(() => saveStartLayout('anna', 'v1'))
  } finally { delete globalThis.localStorage }
})
