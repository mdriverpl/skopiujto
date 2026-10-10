import test from 'node:test'
import assert from 'node:assert/strict'
import { startSummary } from './startSummary.js'

test('counts only assigned outstanding surveys and my pending tasks', () => {
  const result = startSummary([
    { id: 'pending', assigned: true },
    { id: 'answered', assigned: true, submitted_at: '2026-01-01' },
    { id: 'closed', assigned: true, closed_at: '2026-01-01' },
    { id: 'sent', is_owner: true },
  ], { mine: [
    { key: 'folder', status: 'todo', folder_id: 'a' },
    { key: 'edit', status: 'in_progress', document_id: 'b' },
    { key: 'finished', status: 'done', document_id: 'c' },
    { key: 'cancelled', status: 'cancelled', folder_id: 'd' },
  ], sent: [{ key: 'someone-else', status: 'todo', document_id: 'e' }] })
  assert.deepEqual(result.surveys.map(item => item.id), ['pending'])
  assert.equal(result.total, 3)
  assert.equal(result.folders, 1)
  assert.equal(result.files, 1)
})

test('multiple tasks on one resource count once and keep general tasks', () => {
  const result = startSummary([], { mine: [
    { key: 'a', status: 'todo', document_id: 'doc' },
    { key: 'b', status: 'waiting', document_id: 'doc' },
    { key: 'c', status: 'todo', folder_id: 'folder' },
    { key: 'd', status: 'in_progress', folder_id: 'folder' },
    { key: 'e', status: 'todo' },
  ] })
  assert.equal(result.total, 5)
  assert.equal(result.folders, 1)
  assert.equal(result.files, 1)
  assert.equal(result.generalTasks.length, 1)
})

test('file acceptance counts when recipient has no drive document access', () => {
  const result = startSummary([], { mine: [
    { key: 'approval:a', origin: 'approval', status: 'waiting', document_id: null, filename: 'contract.pdf', file_version: 1, sender_id: 'sender' },
    { key: 'approval:b', origin: 'approval', status: 'accepted', filename: 'old.pdf' },
  ] })
  assert.equal(result.files, 1)
  assert.equal(result.generalTasks.length, 0)
  assert.equal(result.total, 1)
})

test('earliest deadline sorts first without mutating input', () => {
  const mine = [
    { key: 'later', status: 'todo', due_at: '2026-11-01' },
    { key: 'old', status: 'todo', created_at: '2026-01-01' },
    { key: 'earlier', status: 'todo', due_at: '2026-10-01' },
    { key: 'new', status: 'todo', created_at: '2026-09-01' },
  ]
  assert.deepEqual(startSummary([], { mine }).tasks.map(item => item.key), ['earlier', 'later', 'new', 'old'])
  assert.equal(mine[0].key, 'later')
  assert.equal(startSummary().total, 0)
})
