export function attachmentSelection(message = {}) {
  return { files: [], drive: [], existing: message.attachments || [], removed: [],
    zip_enabled: !!message.zip_enabled, zip_name: message.zip_name || 'zalaczniki.zip', zip_password: message.zip_password || '' }
}

export function hasAttachmentChanges(selection) {
  return !!(selection.files.length || selection.drive.length || selection.existing.length || selection.removed.length || selection.zip_enabled)
}

export async function saveAttachmentSelection(api, draft, selection) {
  if (!hasAttachmentChanges(selection)) return draft
  const data = new FormData()
  data.append('version', String(draft.version))
  for (const file of selection.files) data.append('files', file, file.name)
  data.append('drive_ids', JSON.stringify(selection.drive.map(file => file.id)))
  data.append('remove_ids', JSON.stringify(selection.removed))
  data.append('zip_enabled', String(selection.zip_enabled))
  data.append('zip_name', selection.zip_name)
  data.append('zip_password', selection.zip_enabled ? selection.zip_password : '')
  return api(`/client-mail/${draft.id}/attachments`, 'POST', data)
}

export async function downloadMailArchive(mailId) {
  const response = await fetch(`/api/client-mail/${mailId}/archive`, { credentials: 'same-origin' })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail || 'Nie udało się pobrać ZIP.')
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const name = response.headers.get('content-disposition')?.match(/filename\*=UTF-8''([^;]+)/)?.[1]
  link.href = url; link.download = name ? decodeURIComponent(name) : 'zalaczniki.zip'
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
