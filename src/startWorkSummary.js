import { dateKey } from './calendarDates.js'

export function startWorkSummary(tasks = [], now = new Date()) {
  const today = dateKey(now)
  const shift = days => {
    const date = new Date(today + 'T12:00:00Z')
    date.setUTCDate(date.getUTCDate() + days)
    return dateKey(date)
  }
  const pending = tasks.filter(item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status))
  const dated = pending.filter(item => item.due_at && dateKey(item.due_at))
  const overdue = dated.filter(item => new Date(item.due_at).getTime() < now.getTime()).length
  const dueToday = dated.filter(item => dateKey(item.due_at) === today).length
  return {
    tasks: pending.length,
    todo: pending.filter(item => item.status === 'todo').length,
    inProgress: pending.filter(item => item.status === 'in_progress').length,
    waiting: pending.filter(item => ['waiting', 'sending'].includes(item.status)).length,
    overdue, dueToday,
    tomorrow: dated.filter(item => dateKey(item.due_at) === shift(1)).length,
    week: dated.filter(item => dateKey(item.due_at) >= today && dateKey(item.due_at) <= shift(6)).length,
    undated: pending.length - dated.length
  }
}
