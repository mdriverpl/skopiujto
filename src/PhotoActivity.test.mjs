import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { reactive, ref } from 'vue'

const source = compileScript(parse(readFileSync(new URL('./PhotoActivity.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'photo-activity-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
const initial = { liked: false, likes_count: 2, comments_count: 0, comments: [], has_more: false }
function activity(api) {
  const cleanups = [], events = []
  const context = { ref, onMounted() {}, onBeforeUnmount: fn => cleanups.push(fn),
    localStorage: { getItem() { return null }, setItem() {} } }
  for (const icon of ['Heart', 'MessageSquare', 'Pencil', 'Send', 'Trash2', 'X']) context[icon] = {}
  runInNewContext(source, context)
  const props = reactive({ api, token: 'link-token', canEdit: true,
    photo: { id: 'photo', title: 'Old title', description: 'Old description', caption_version: 3 } })
  const state = context.component.setup(props, { expose() {}, emit: (...args) => events.push(args) })
  return { state, props, events, unmount: () => cleanups.forEach(fn => fn()) }
}

test('likes wait for visitor initialization, block duplicate requests and can be undone', async () => {
  const calls = []; let resolveLike
  const { state, events } = activity(async (path, method, body) => {
    calls.push({ path, method, body })
    if (!method) return { ...initial }
    return new Promise(resolve => { resolveLike = resolve })
  })
  await state.toggleLike(); assert.equal(calls.length, 0)
  await state.load()
  const pending = state.toggleLike(); await state.toggleLike()
  assert.equal(calls.length, 2); assert.equal(calls[1].body.liked, true)
  resolveLike({ liked: true, likes_count: 3, comments_count: 0 }); await pending
  assert.equal(state.liked.value, true)
  assert.equal(events.at(-1)[1].likes_count, 3)
  const undo = state.toggleLike(); assert.equal(calls[2].body.liked, false)
  resolveLike({ liked: false, likes_count: 2, comments_count: 0 }); await undo
  assert.equal(state.liked.value, false)
})

test('failed comments preserve the draft and retry adds one escaped-text record', async () => {
  let fail = true
  const { state, events } = activity(async (path, method, body) => {
    if (!method) return { ...initial }
    if (fail) throw new Error('Offline')
    return { id: 'new', ...body, mine: true, created_at: new Date().toISOString() }
  })
  await state.load(); state.author.value = ' Anna '; state.content.value = '<script>test</script>'
  await state.send()
  assert.equal(state.content.value, '<script>test</script>'); assert.equal(state.error.value, 'Offline')
  fail = false; await state.send()
  assert.equal(state.comments.value[0].author, 'Anna')
  assert.equal(state.comments.value[0].content, '<script>test</script>')
  assert.equal(state.content.value, ''); assert.equal(events.at(-1)[1].comments_count, 1)
})

test('caption conflicts keep edits and successful saves use the caption version', async () => {
  let fail = true; const calls = []
  const { state, events } = activity(async (path, method, body) => {
    calls.push({ path, method, body })
    if (fail) throw new Error('Conflict')
    return { id: 'photo', ...body, caption_version: 4 }
  })
  state.edit(); state.title.value = ' New title '; state.description.value = ' New description '
  await state.save(); assert.equal(state.editing.value, true); assert.equal(state.title.value, ' New title ')
  fail = false; await state.save()
  assert.equal(calls[1].method, 'PATCH'); assert.equal(calls[1].body.version, 3)
  assert.equal(calls[1].body.title, 'New title'); assert.equal(state.editing.value, false)
  assert.equal(events.at(-1)[0], 'caption-saved')
})

test('own deletion uses the public route and owner moderation uses the authenticated route', async () => {
  const calls = []
  const { state } = activity(async (path, method) => { calls.push({ path, method }); return { ...initial } })
  await state.load()
  state.comments.value = [{ id: 'own', mine: true }, { id: 'foreign', mine: false }]; state.count.value = 2
  await state.remove(state.comments.value[0]); await state.remove(state.comments.value[0])
  assert.equal(calls[1].path, '/public-shares/link-token/documents/photo/comments/own')
  assert.equal(calls[2].path, '/gallery-comments/foreign')
  assert.equal(state.count.value, 0)
})

test('a response for a closed photo cannot overwrite another photo activity', async () => {
  let resolve
  const { state, events, unmount } = activity(() => new Promise(done => { resolve = done }))
  const pending = state.load(); unmount(); const count = events.length
  resolve({ ...initial, likes_count: 100 }); await pending
  assert.equal(events.length, count); assert.equal(state.likes.value, 0)
})
