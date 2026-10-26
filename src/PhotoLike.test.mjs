import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { reactive, ref } from 'vue'
const source = compileScript(parse(readFileSync(new URL('./PhotoLike.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'photo-like-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function heart(api) {
  const events = [], props = reactive({ api, token: 'link', photo: { id: 'photo', title: 'Photo', liked: false, likes_count: 2 } })
  const context = { ref, Heart: {} }; runInNewContext(source, context)
  const state = context.component.setup(props, { expose() {}, emit(name, result) { events.push({ name, result }); Object.assign(props.photo, result) } })
  return { state, props, events }
}

test('a card heart toggles on and off through the shared photo API', async () => {
  const calls = []
  const { state, props, events } = heart(async (path, method, body) => { calls.push({ path, method, body }); return { liked: body.liked, likes_count: body.liked ? 3 : 2 } })
  await state.toggle(); assert.equal(props.photo.liked, true); assert.equal(props.photo.likes_count, 3)
  await state.toggle(); assert.equal(props.photo.liked, false); assert.equal(props.photo.likes_count, 2)
  assert.equal(calls[0].path, '/public-shares/link/documents/photo/like'); assert.equal(calls[0].method, 'PUT')
  assert.equal(calls[1].body.liked, false); assert.equal(events[0].name, 'updated')
})

test('failed liking preserves the count and current selection for retry', async () => {
  let fail = true
  const { state, props } = heart(async () => { if (fail) throw new Error('Offline'); return { liked: true, likes_count: 3 } })
  await state.toggle(); assert.equal(props.photo.liked, false); assert.equal(props.photo.likes_count, 2)
  assert.equal(state.error.value, 'Offline'); assert.equal(state.busy.value, false)
  fail = false; await state.toggle(); assert.equal(props.photo.liked, true); assert.equal(state.error.value, '')
})

test('a pending like blocks repeated clicks until the server responds', async () => {
  let done, count = 0
  const { state } = heart(() => { count++; return new Promise(resolve => { done = resolve }) })
  const pending = state.toggle(); await state.toggle(); assert.equal(count, 1)
  done({ liked: true, likes_count: 3 }); await pending; assert.equal(state.busy.value, false)
})
