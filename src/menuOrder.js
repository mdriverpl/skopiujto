export const defaultMenuOrder = ['start', 'ai', 'mail', 'tasks', 'calendar', 'notes', 'documents', 'surveys', 'drive', 'templates', 'dictionaries', 'admin']

export function normalizeMenuOrder(value) {
  const known = Array.isArray(value) ? value.filter(id => defaultMenuOrder.includes(id)) : []
  return [...new Set([...known, ...defaultMenuOrder])]
}

export function moveMenuItem(order, source, target, after = false) {
  if (source === target || !order.includes(source) || !order.includes(target)) return [...order]
  const result = order.filter(id => id !== source)
  result.splice(result.indexOf(target) + (after ? 1 : 0), 0, source)
  return result
}
