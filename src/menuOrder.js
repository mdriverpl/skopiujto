export const defaultMenuOrder = ['start', 'mail', 'planning', 'documents', 'dictionaries', 'help', 'settings']
const parentMenu = { admin: 'settings', 'mail-settings': 'settings', 'edelivery-settings': 'settings', drive: 'documents', edelivery: 'mail', tasks: 'planning', calendar: 'planning', notes: 'planning', surveys: 'documents', templates: 'documents' }

export function normalizeMenuOrder(value) {
  const known = Array.isArray(value) ? value.map(id => parentMenu[id] || id).filter(id => defaultMenuOrder.includes(id)) : []
  return [...new Set([...known, ...defaultMenuOrder])]
}

export function moveMenuItem(order, source, target, after = false) {
  if (source === target || !order.includes(source) || !order.includes(target)) return [...order]
  const result = order.filter(id => id !== source)
  result.splice(result.indexOf(target) + (after ? 1 : 0), 0, source)
  return result
}
