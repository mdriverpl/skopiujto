const pending = new Set(['todo', 'in_progress', 'waiting', 'sending'])
export function startSummary(surveys = [], data = {}) {
  const tasks = [...new Map((data.mine || []).filter(item => pending.has(item.status)).map(item => [item.key || item.id, item])).values()]
  const outstandingSurveys = surveys.filter(item => item.assigned && !item.submitted_at && !item.closed_at)
  const folderTasks = tasks.filter(item => item.folder_id)
  const fileTasks = tasks.filter(item => item.document_id || item.origin === 'approval')
  const generalTasks = tasks.filter(item => !item.folder_id && !item.document_id && item.origin !== 'approval')
  const ordered = [...tasks].sort((a, b) => {
    const first = a.due_at ? new Date(a.due_at).getTime() : Infinity
    const second = b.due_at ? new Date(b.due_at).getTime() : Infinity
    return first - second || (b.created_at || '').localeCompare(a.created_at || '')
  })
  return { surveys: outstandingSurveys, folderTasks, fileTasks, generalTasks, tasks: ordered,
    folders: new Set(folderTasks.map(item => item.folder_id)).size,
    files: new Set(fileTasks.map(item => item.document_id || `approval:${JSON.stringify([item.sender_id, item.filename || item.title, item.file_version])}`)).size,
    total: tasks.length + outstandingSurveys.length }
}
