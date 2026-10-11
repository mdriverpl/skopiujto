const warsawDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit',
})
export function dateKey(value) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const parts = Object.fromEntries(warsawDate.formatToParts(date).map(part => [part.type, part.value]))
  return parts.year + '-' + parts.month + '-' + parts.day
}
export function monthDays(year, month) {
  const first = new Date(year, month, 1, 12)
  const offset = (first.getDay() + 6) % 7
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(year, month, 1 - offset + index, 12)
    // Grid dates are calendar labels, independent of the computer's timezone.
    const key = date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0')
    return { key, day: date.getDate(), inMonth: date.getMonth() === month }
  })
}