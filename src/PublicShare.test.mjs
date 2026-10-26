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
    'AlertCircle', 'Share2', 'ImagePlus', 'RichTextEditor', 'PhotoGallery', 'PhotoUpload', 'ShareLink', 'PhotoLike']) context[name] = {}
  runInNewContext(source, context)
  const state = context.component.setup({ api, token: 'gallery-token' }, { expose() {} })
  return { state, mount: () => mount() }
}
const root = { kind: 'folder', title: 'Gallery', folder_id: 'child', files: [{ id: 'one', image: true, title: 'Photo' }],
  view_mode: 'gallery', link_id: 'link', can_add_photos: true, allow_uploads: false }

test('deep links load the scoped folder before opening the selected photo', async () => {
  const paths = [], opened = []
  const { state, mount } = page(async path => { paths.push(path); return path.endsWith('/permissions') ? { can_edit: false } : { ...root } }, '?folder=child&photo=one')
  state.gallery.value = { open: id => opened.push(id) }; await mount()
  assert.ok(paths.includes('/public-shares/gallery-token?folder_id=child'))
  assert.deepEqual(opened, ['one'])
  state.shareResource(root.files[0]); const address = new URL(state.shared.value.url)
  assert.equal(address.searchParams.get('folder'), 'child'); assert.equal(address.searchParams.get('photo'), 'one')
  state.shareResource(); assert.equal(new URL(state.shared.value.url).searchParams.has('photo'), false)
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
