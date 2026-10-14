import test from 'node:test'
import assert from 'node:assert/strict'
import { ensureDocumentsFolder, findDocumentsFolder } from './documentsFolder.js'

const root = { id: 'documents', name: 'Dokumenty', parent_id: null, user_id: 'me', permissions: { read: true, add: true } }

test('Documents selects the root folder, preferring the current owner over a shared namesake', () => {
  const shared = { ...root, id: 'shared', user_id: 'other' }
  const child = { ...root, id: 'nested', parent_id: 'other-folder' }
  assert.equal(findDocumentsFolder([child, shared, root], 'me').id, 'documents')
  assert.equal(findDocumentsFolder([child], 'me'), undefined)
  assert.equal(findDocumentsFolder([{ ...root, name: 'DOKUMENTY' }], 'me').id, 'documents')
})

test('opening an existing Documents root does not create another folder', async () => {
  const calls = []
  const result = await ensureDocumentsFolder(async (...args) => { calls.push(args); return [root] }, 'me')
  assert.equal(result.folder.id, root.id)
  assert.deepEqual(calls, [['/folders']])
})

test('missing Documents is created at disk root with private access', async () => {
  const calls = []
  const result = await ensureDocumentsFolder(async (...args) => {
    calls.push(args)
    return calls.length === 1 ? [] : args[1] === 'POST' ? { id: root.id } : [root]
  }, 'me')
  assert.deepEqual(calls[1], ['/folders', 'POST', { name: 'Dokumenty', parent_id: null, access_mode: 'private' }])
  assert.equal(result.folder.permissions.add, true)
})

test('concurrent creation reuses the folder after a naming conflict', async () => {
  let calls = 0
  const result = await ensureDocumentsFolder(async (path, method) => {
    calls++
    if (method === 'POST') throw Object.assign(new Error('Already exists'), { status: 409 })
    return calls === 1 ? [] : [root]
  }, 'me')
  assert.equal(result.folder.id, root.id)
  assert.equal(calls, 3)
})

test('missing creation permission propagates instead of opening the entire disk', async () => {
  await assert.rejects(ensureDocumentsFolder(async (path, method) => {
    if (method === 'POST') throw Object.assign(new Error('Brak uprawnienia'), { status: 403 })
    return []
  }, 'me'), /Brak uprawnienia/)
  await assert.rejects(ensureDocumentsFolder(async () => [{ ...root, permissions: { read: false } }], 'me'), /Brak dostępu/)
})
