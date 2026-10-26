import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, nextTick, ref } from 'vue'

const source = compileScript(parse(readFileSync(new URL('./PublicShare.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'public-share-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function page(api, search = '') {
  let mount
  const context = { computed, nextTick, ref, URL, URLSearchParams, location: { origin: 'https://example.com', search },
    onMounted: callback => { mount = callback } }
  for (const name of ['Folder', 'FileText', 'Download', 'ChevronRight', 'ArrowLeft', 'Link', 'Images', 'LayoutGrid',
    'AlertCircle', 'ImagePlus', 'RichTextEditor', 'PhotoGallery', 'PhotoUpload', 'PhotoLike']) context[name] = {}
  runInNewContext(source, context)
  const state = context.component.setup({ api, token: 'gallery-token' }, { expose() {} })
  return { state, mount: () => mount() }
}
const root = { kind: 'folder', title: 'Gallery', folder_id: 'child', files: [{ id: 'one', image: true, title: 'Photo' }],
  view_mode: 'gallery', link_id: 'link', can_add_photos: true, allow_uploads: false }

test('opening a link enters a single nested folder but manual breadcrumb navigation stays at the chosen level', async () => {
  const calls = []
  const { state, mount } = page(async path => {
    calls.push(path)
    if (path.endsWith('/permissions')) return { can_edit: false }
    if (path.includes('folder_id=year')) return { ...root, folder_id: 'year', files: [], folders: [{ id: 'album' }] }
    if (path.includes('folder_id=album')) return { ...root, folder_id: 'album', files: root.files, folders: [] }
    return { ...root, folder_id: 'root', files: [], folders: [{ id: 'year', name: '2021' }] }
  })
  await mount(); assert.equal(state.resource.value.folder_id, 'album')
  assert.ok(calls.includes('/public-shares/gallery-token?folder_id=year'))
  assert.ok(calls.includes('/public-shares/gallery-token?folder_id=album'))
  await state.load('root'); assert.equal(state.resource.value.folder_id, 'root')
})

test('automatic entry stops at files, multiple choices and cyclic folder responses', async () => {
  for (const variant of ['files', 'choices', 'cycle']) {
    const calls = []
    const { state, mount } = page(async path => {
      if (path.endsWith('/permissions')) return { can_edit: false }
      calls.push(path)
      return { ...root, folder_id: 'root', files: variant === 'files' ? root.files : [],
        folders: variant === 'choices' ? [{ id: 'a' }, { id: 'b' }] : [{ id: 'root' }] }
    })
    await mount(); assert.equal(calls.length, 1); assert.equal(state.resource.value.folder_id, 'root')
  }
})

test('an explicitly linked folder is respected even when it contains a single child', async () => {
  const calls = []
  const { state, mount } = page(async path => {
    if (path.endsWith('/permissions')) return { can_edit: false }
    calls.push(path)
    return { ...root, folder_id: 'root', files: [], folders: [{ id: 'year', name: '2021' }] }
  }, '?folder=root')
  await mount(); assert.equal(calls.length, 1); assert.equal(state.resource.value.folder_id, 'root')
})

test('GPS and metadata share a single request per file version and failed requests can retry', async () => {
  let calls = 0, fail = true
  const { state } = page(async () => { calls++; if (fail) throw new Error('Offline'); return { width: 12, location: { latitude: 1, longitude: 2 } } })
  const photo = { id: 'one', version: 1 }
  await assert.rejects(state.photoMetadata(photo), /Offline/)
  fail = false
  const [metadata, point] = await Promise.all([state.photoMetadata(photo), state.photoLocation(photo)])
  assert.equal(calls, 2); assert.equal(metadata.width, 12); assert.equal(point.location.latitude, 1)
  await state.photoMetadata({ ...photo, version: 2 }); assert.equal(calls, 3)
})

test('deep links load the scoped folder before opening the selected photo', async () => {
  const paths = [], opened = []
  const { state, mount } = page(async path => { paths.push(path); return path.endsWith('/permissions') ? { can_edit: false } : { ...root } }, '?folder=child&photo=one')
  state.gallery.value = { open: id => opened.push(id) }; await mount()
  assert.ok(paths.includes('/public-shares/gallery-token?folder_id=child'))
  assert.deepEqual(opened, ['one'])
})

test('a photo outside the current folder cannot be opened by changing the URL', async () => {
  const { state, mount } = page(async path => path.endsWith('/permissions') ? { can_edit: false } : { ...root }, '?photo=outside')
  state.gallery.value = { open: () => assert.fail('outside photo must not open') }; await mount()
  assert.equal(state.canUploadPhotos.value, false)
  state.resource.value.allow_uploads = true; assert.equal(state.canUploadPhotos.value, true)
  state.resource.value.can_add_photos = false; assert.equal(state.canUploadPhotos.value, false)
})

test('owner upload controls work while guest uploads are disabled and newly uploaded photos are not duplicated', async () => {
  const { state, mount } = page(async path => {
    return path.endsWith('/permissions') ? { can_edit: true } : { ...root, files: [] }
  })
  await mount(); assert.equal(state.canUploadPhotos.value, true)
  state.uploaded({ id: 'added', image: true }); state.uploaded({ id: 'added', image: true })
  assert.equal(state.resource.value.files.length, 1)
})
