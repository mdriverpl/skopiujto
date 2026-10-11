import test from 'node:test'
import assert from 'node:assert/strict'
import { dateKey, monthDays } from './calendarDates.js'
test('deadlines use Warsaw dates around midnight and DST', () => {
  assert.equal(dateKey('2026-01-01T23:30:00Z'), '2026-01-02')
  assert.equal(dateKey('2026-07-01T22:30:00Z'), '2026-07-02')
  assert.equal(dateKey('2026-03-29T00:30:00Z'), '2026-03-29')
  assert.equal(dateKey('invalid'), null)
})
test('February calendar includes leap day and starts on Monday', () => {
  const cells = monthDays(2024, 1)
  assert.equal(cells.length, 42)
  assert.equal(cells[0].key, '2024-01-29')
  assert.equal(cells.filter(day => day.inMonth).length, 29)
  assert.equal(cells.find(day => day.key === '2024-02-29').inMonth, true)
  assert.equal(cells[41].key, '2024-03-10')
})
test('calendar crosses the year boundary and handles Sunday month starts', () => {
  const cells = monthDays(2026, 10)
  assert.equal(cells[0].key, '2026-10-26')
  assert.equal(cells[6].key, '2026-11-01')
  assert.equal(cells.filter(day => day.inMonth).length, 30)
  const january = monthDays(2027, 0)
  assert.equal(january[0].key, '2026-12-28')
})