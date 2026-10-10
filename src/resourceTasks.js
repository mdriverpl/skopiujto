export function resourceTasks(data, resource, type = 'folder') {
  if (!resource?.id) return []
  const unique = new Map()
  for (const item of [...(data?.mine || []), ...(data?.sent || [])]) {
    const matches = type === 'file' ? item.document_id === resource.id : item.origin === 'task' && item.folder_id === resource.id
    if (matches) unique.set(item.key, item)
  }
  const pending = item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status)
  return [...unique.values()].sort((a, b) => Number(pending(b)) - Number(pending(a)) || b.created_at.localeCompare(a.created_at))
}
