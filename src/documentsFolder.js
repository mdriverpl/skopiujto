export function findDocumentsFolder(folders, userId) {
  const roots = folders.filter(folder => folder.parent_id == null && folder.name.toLocaleLowerCase('pl') === 'dokumenty')
  return roots.find(folder => folder.user_id === userId) || roots.find(folder => folder.permissions?.read)
}

export async function ensureDocumentsFolder(api, userId) {
  let folders = await api('/folders')
  let folder = findDocumentsFolder(folders, userId)
  if (!folder) {
    try {
      await api('/folders', 'POST', { name: 'Dokumenty', parent_id: null, access_mode: 'private' })
    } catch (error) {
      if (error.status !== 409) throw error
    }
    folders = await api('/folders')
    folder = findDocumentsFolder(folders, userId)
  }
  if (!folder?.permissions?.read) throw new Error('Brak dostępu do katalogu Dokumenty.')
  return { folder, folders }
}
