<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Heart, MessageSquare, Pencil, Send, Trash2, X } from 'lucide-vue-next'
const props = defineProps({ api: Function, token: String, photo: Object, canEdit: Boolean })
const emit = defineEmits(['state', 'caption-saved', 'close'])
const loading = ref(true), busy = ref(false), error = ref(''), liked = ref(false)
const ready = ref(false)
const likes = ref(props.photo.likes_count || 0), count = ref(props.photo.comments_count || 0)
const comments = ref([]), hasMore = ref(false), paging = ref(false)
const author = ref(''), content = ref(''), sending = ref(false), deleting = ref(null)
const editing = ref(false), saving = ref(false), title = ref(props.photo.title), description = ref(props.photo.description || '')
let alive = true
try { author.value = localStorage.getItem('gallery-comment-name') || '' } catch {}
const base = `/public-shares/${encodeURIComponent(props.token)}/documents/${encodeURIComponent(props.photo.id)}`
function announce() { if (alive) emit('state', { id: props.photo.id, liked: liked.value, likes_count: likes.value, comments_count: count.value, loading: loading.value || !ready.value, busy: busy.value }) }
async function load() {
  loading.value = true; error.value = ''; announce()
  try {
    const result = await props.api(`${base}/activity`)
    if (!alive) return
    liked.value = result.liked; likes.value = result.likes_count; count.value = result.comments_count
    comments.value = result.comments; hasMore.value = result.has_more; ready.value = true
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) { loading.value = false; announce() } }
}
async function toggleLike() {
  if (!ready.value || loading.value || busy.value) return
  busy.value = true; error.value = ''; announce()
  try {
    const result = await props.api(`${base}/like`, 'PUT', { liked: !liked.value })
    if (!alive) return
    liked.value = result.liked; likes.value = result.likes_count; count.value = result.comments_count
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) { busy.value = false; announce() } }
}
async function send() {
  if (!ready.value || sending.value || loading.value || !author.value.trim() || !content.value.trim()) return
  sending.value = true; error.value = ''
  try {
    const comment = await props.api(`${base}/comments`, 'POST', { author: author.value.trim(), content: content.value.trim() })
    if (!alive) return
    comments.value.push(comment); count.value++; content.value = ''; announce()
    try { localStorage.setItem('gallery-comment-name', author.value.trim()) } catch {}
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) sending.value = false }
}
async function remove(comment) {
  if (deleting.value) return
  deleting.value = comment.id; error.value = ''
  try {
    await props.api(comment.mine ? `${base}/comments/${comment.id}` : `/gallery-comments/${comment.id}`, 'DELETE')
    if (!alive) return
    comments.value = comments.value.filter(item => item.id !== comment.id); count.value--; announce()
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) deleting.value = null }
}
async function older() {
  if (paging.value) return
  paging.value = true; error.value = ''
  try {
    const result = await props.api(`${base}/activity?offset=${comments.value.length}`)
    if (!alive) return
    const existing = new Set(comments.value.map(item => item.id))
    comments.value.unshift(...result.comments.filter(item => !existing.has(item.id)))
    hasMore.value = result.has_more; count.value = result.comments_count; announce()
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) paging.value = false }
}
async function save() {
  if (saving.value || !title.value.trim()) return
  saving.value = true; error.value = ''
  try {
    const photo = await props.api(`${base}/caption`, 'PATCH', { title: title.value.trim(), description: description.value.trim(), version: props.photo.caption_version || 0 })
    if (alive) { emit('caption-saved', photo); editing.value = false }
  } catch (err) { if (alive) error.value = err.message }
  finally { if (alive) saving.value = false }
}
function edit() { title.value = props.photo.title; description.value = props.photo.description || ''; editing.value = true }
function commentLabel(value) { return ({ one: 'komentarz', few: 'komentarze', many: 'komentarzy', other: 'komentarza' })[new Intl.PluralRules('pl').select(value)] }
const date = value => new Date(value).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })
onMounted(load)
onBeforeUnmount(() => { alive = false })
defineExpose({ toggleLike })
</script>
<template>
  <aside class="photo-activity" aria-label="Opis i komentarze zdjęcia">
    <header><strong><MessageSquare :size="17" />Opis i komentarze</strong><button aria-label="Ukryj komentarze" @click="emit('close')"><X :size="18" /></button></header>
    <div class="activity-scroll">
      <form v-if="editing" class="caption-form" @submit.prevent="save">
        <label>Nazwa zdjęcia<input v-model="title" maxlength="200" required :disabled="saving" /></label>
        <label>Krótki opis<textarea v-model="description" maxlength="500" rows="3" :disabled="saving"></textarea><small>{{ description.length }}/500</small></label>
        <div class="caption-actions"><button type="submit" :disabled="saving || !title.trim()">{{ saving ? 'Zapisywanie…' : 'Zapisz' }}</button><button type="button" :disabled="saving" @click="editing = false">Anuluj</button></div>
      </form>
      <section v-else class="photo-details"><h3>{{ photo.title }}</h3><p v-if="photo.description">{{ photo.description }}</p><p v-else class="activity-muted">Brak opisu zdjęcia.</p><button v-if="canEdit" class="caption-edit" @click="edit"><Pencil :size="14" />Edytuj nazwę i opis</button></section>
      <div class="activity-summary"><button :aria-pressed="liked" :disabled="!ready || loading || busy" @click="toggleLike"><Heart :size="17" :fill="liked ? 'currentColor' : 'none'" />{{ liked ? 'Lubisz to' : 'Lubię to' }} · {{ likes }}</button><span>{{ count }} {{ commentLabel(count) }}</span></div>
      <p v-if="error" class="activity-error" role="alert">{{ error }} <button @click="load">Odśwież</button></p>
      <p v-if="loading" class="activity-muted" role="status">Wczytywanie komentarzy…</p>
      <template v-else>
        <button v-if="hasMore" class="older-comments" :disabled="paging" @click="older">{{ paging ? 'Wczytywanie…' : 'Wcześniejsze komentarze' }}</button>
        <p v-if="!comments.length" class="activity-muted">Dodaj pierwszy komentarz do tego zdjęcia.</p>
        <ol class="photo-comments"><li v-for="comment in comments" :key="comment.id"><div><strong>{{ comment.author }}</strong><button v-if="comment.mine || canEdit" :disabled="!!deleting" :aria-label="`Usuń komentarz: ${comment.author}`" @click="remove(comment)"><Trash2 :size="14" /></button></div><time>{{ date(comment.created_at) }}</time><p>{{ comment.content }}</p></li></ol>
      </template>
    </div>
    <form class="comment-form" @submit.prevent="send"><label>Twoja nazwa<input v-model="author" maxlength="80" autocomplete="nickname" placeholder="Jak się podpiszesz?" required :disabled="sending" /></label><label>Komentarz<textarea v-model="content" rows="2" maxlength="1000" placeholder="Napisz coś o zdjęciu…" required :disabled="sending"></textarea></label><div><small>{{ content.length }}/1000 · Podpis wybrany przez autora</small><button type="submit" :disabled="!ready || sending || loading || !author.trim() || !content.trim()"><Send :size="15" />{{ sending ? 'Wysyłanie…' : 'Dodaj' }}</button></div></form>
  </aside>
</template>
<style scoped>
.photo-activity { display:flex; flex-direction:column; flex:0 0 350px; width:350px; min-height:0; background:#171b25; border-left:1px solid #ffffff18; color:#e5eaf6; font-size:12px; }
.photo-activity button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid transparent; border-radius:7px; padding:8px; background:transparent; color:#e5eaf6; font:inherit; cursor:pointer; }.photo-activity button:hover { background:#ffffff13; }.photo-activity button:disabled { opacity:.4; cursor:default; }.photo-activity button:focus-visible { outline:2px solid #b49bff; outline-offset:2px; }
header { display:flex; align-items:center; justify-content:space-between; padding:10px 14px; border-bottom:1px solid #ffffff14; flex-shrink:0; }header strong { display:flex; gap:8px; align-items:center; font-weight:500; }
.activity-scroll { overflow-y:auto; min-height:0; flex:1; padding:16px; scrollbar-width:thin; }.photo-details h3 { margin:0 0 10px; font-size:15px; overflow-wrap:anywhere; }.photo-details p,.photo-comments p { white-space:pre-wrap; line-height:1.6; overflow-wrap:anywhere; }.activity-muted { color:#a4adbf; font-size:11px; line-height:1.6; }.activity-summary { display:flex; align-items:center; gap:12px; margin:18px 0; }.activity-summary>span { color:#a4adbf; font-size:11px; }
.photo-activity button { font-size:11px; }.photo-activity .caption-edit { padding:7px 0; color:#cbb6ff; }.photo-activity .activity-summary button { padding:8px; border:1px solid #ffffff22; }.photo-activity button[aria-pressed=true] { color:#ff9eb7; background:#f4769c18; }
label { display:flex; flex-direction:column; gap:6px; color:#bac6db; font-size:11px; }input,textarea { box-sizing:border-box; width:100%; border:1px solid #ffffff26; border-radius:7px; padding:9px 10px; background:#0e1119; color:#f7f8fc; font:inherit; font-size:12px; }textarea { resize:vertical; min-height:55px; max-height:180px; }input:focus,textarea:focus { outline:2px solid #b49bff; outline-offset:1px; }small { font-size:9px; color:#a4adbf; }.caption-form { display:grid; gap:12px; }.caption-actions { display:flex; gap:8px; }.photo-activity .caption-actions button:first-child,.photo-activity .comment-form button { background:#7654b8; color:white; }
.photo-comments { margin:0; padding:0; list-style:none; }.photo-comments li { padding:12px 0; border-bottom:1px solid #ffffff14; }.photo-comments li>div { display:flex; align-items:center; justify-content:space-between; gap:10px; }.photo-comments strong { font-size:12px; overflow-wrap:anywhere; }.photo-comments time { color:#8894ab; font-size:9px; }.photo-comments p { margin:8px 0 0; }.photo-comments button { padding:5px; }.comment-form { display:grid; gap:9px; padding:14px; border-top:1px solid #ffffff18; flex-shrink:0; }.comment-form>div { display:flex; align-items:center; justify-content:space-between; gap:8px; }.comment-form small { max-width:160px; line-height:1.5; }.activity-error { color:#ffb4be; line-height:1.6; }.photo-activity .older-comments { border:1px solid #ffffff22; width:100%; }
@media(max-width:800px) { .photo-activity { width:100%; flex:1 1 52%; min-height:220px; max-height:55dvh; border-left:0; border-top:1px solid #ffffff18; }.comment-form { padding:10px 14px; gap:6px; }.comment-form label:first-child { flex-direction:row; align-items:center; }.comment-form input { flex:1; min-width:0; }.comment-form textarea { min-height:45px; height:45px; }.photo-activity header { padding:4px 14px; }.activity-scroll { padding:10px 14px; } }
</style>
