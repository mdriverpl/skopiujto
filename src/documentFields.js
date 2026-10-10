const pattern = /\[([^\[\]\r\n]{1,120})\]/g
export const fieldKey = label => label.trim().replace(/\s+/g, ' ').toLocaleLowerCase('pl')
export function plainDocument(text = '') {
  return { type: 'doc', content: text.split('\n').map(line => ({ type: 'paragraph', ...(line ? { content: [{ type: 'text', text: line }] } : {}) })) }
}
export function documentText(node) {
  if (node.type === 'text') return node.text
  if (node.type === 'hardBreak') return '\n'
  return (node.content || []).map(documentText).join(['paragraph', 'heading'].includes(node.type) ? '' : '\n')
}
export function documentFields(source) {
  const fields = new Map()
  for (const match of documentText(source).matchAll(pattern)) {
    const label = match[1].trim().replace(/\s+/g, ' '), key = fieldKey(label)
    if (key && !fields.has(key)) fields.set(key, { key, label })
  }
  return [...fields.values()]
}
export function fillDocument(source, values) {
  function visit(node) {
    if (!node.content) return { ...node }
    if (['paragraph', 'heading'].includes(node.type)) {
      const runs = [], output = []
      let offset = 0
      for (const child of node.content) {
        const text = child.type === 'hardBreak' ? '\n' : child.text || ''
        runs.push({ node: child, start: offset, end: offset + text.length }); offset += text.length
      }
      const text = node.content.map(child => child.type === 'hardBreak' ? '\n' : child.text || '').join('')
      function copy(start, end) {
        for (const run of runs) {
          const a = Math.max(start, run.start), b = Math.min(end, run.end)
          if (a < b) output.push(run.node.type === 'hardBreak' ? { ...run.node } : { ...run.node, text: run.node.text.slice(a - run.start, b - run.start) })
        }
      }
      let cursor = 0
      for (const match of text.matchAll(pattern)) {
        const value = values[fieldKey(match[1])]
        if (typeof value !== 'string' || !value.trim()) continue
        copy(cursor, match.index)
        const original = runs.find(run => run.start <= match.index && run.end > match.index)?.node
        output.push({ ...original, type: 'text', text: value })
        cursor = match.index + match[0].length
      }
      copy(cursor, text.length)
      const result = { ...node, content: output }
      if (!output.length) delete result.content
      return result
    }
    return { ...node, content: node.content.map(visit) }
  }
  return visit(source)
}
