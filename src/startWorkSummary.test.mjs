import test from 'node:test'
import assert from 'node:assert/strict'
import { startWorkSummary } from './startWorkSummary.js'

test('task and calendar counters include only pending tasks and use Polish calendar dates', () => {
  const stats = startWorkSummary([
    { status: 'todo', due_at: '2026-10-15T21:59:59Z' },
    { status: 'in_progress', due_at: '2026-10-15T22:00:00Z' },
    { status: 'waiting', due_at: '2026-10-16T15:00:00Z' },
    { status: 'sending', due_at: '2026-10-16T22:00:00Z' },
    { status: 'todo', due_at: '2026-10-22T12:00:00Z' },
    { status: 'todo', due_at: '2026-10-23T12:00:00Z' },
    { status: 'todo' }, { status: 'todo', due_at: 'invalid' },
    { status: 'done', due_at: '2026-10-16T10:00:00Z' },
    { status: 'cancelled', due_at: '2026-10-16T10:00:00Z' }
  ], new Date('2026-10-16T12:00:00Z'))
  assert.deepEqual(stats, { tasks: 8, todo: 5, inProgress: 1, waiting: 2,
    overdue: 2, dueToday: 2, tomorrow: 1, week: 4, undated: 2 })
})

test('empty dashboard has zero counters and seven-day window survives winter time change', () => {
  assert.ok(Object.values(startWorkSummary([], new Date('2026-10-16T12:00:00Z'))).every(count => count === 0))
  const stats = startWorkSummary([
    { status: 'todo', due_at: '2026-10-25T22:30:00Z' },
    { status: 'todo', due_at: '2026-10-26T00:30:00Z' },
    { status: 'todo', due_at: '2026-10-31T22:59:00Z' },
    { status: 'todo', due_at: '2026-10-31T23:00:00Z' }
  ], new Date('2026-10-25T12:00:00Z'))
  assert.equal(stats.dueToday, 1)
  assert.equal(stats.tomorrow, 1)
  assert.equal(stats.week, 3)
})
