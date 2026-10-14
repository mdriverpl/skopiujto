<script setup>
import { computed, onMounted, ref } from 'vue'
import { Plus, Search, RefreshCw, Pencil, Trash2, X, Save, Building2 } from 'lucide-vue-next'
const props = defineProps({ api: Function })
const items = ref([]), search = ref(''), draft = ref(null), busy = ref(false), error = ref('')
const filtered = computed(() => items.value.filter(item => `${item.name} ${item.nip} ${item.address} ${item.email}`.toLocaleLowerCase('pl').includes(search.value.trim().toLocaleLowerCase('pl'))))
async function run(action) { if (busy.value) return; busy.value = true; error.value = ''; try { await action() } catch (err) { error.value = err.message } finally { busy.value = false } }
async function load() { items.value = await props.api('/admin/companies') }
function edit(item) { if (busy.value) return; error.value = ''; draft.value = item ? { ...item } : { name: '', nip: '', address: '', email: '', phone: '' } }
async function save() {
  if (!draft.value?.name.trim()) return
  await run(async () => { const item = draft.value; await props.api(item.id ? `/admin/companies/${item.id}` : '/admin/companies', item.id ? 'PATCH' : 'POST', { name: item.name.trim(), nip: item.nip, address: item.address, email: item.email, phone: item.phone, ...(item.id ? { version: item.version } : {}) }); draft.value = null; await load() })
}
async function remove(item) { if (busy.value || !window.confirm(`Usunąć firmę „${item.name}”? Firma z kontami lub grupami nie może zostać usunięta.`)) return; await run(async () => { await props.api(`/admin/companies/${item.id}`, 'DELETE'); await load() }) }
onMounted(() => run(load))
</script>
<template>
  <section class="companies-page">
    <Teleport to="#workspace-title"><div><h1>Katalog firm</h1><p>Firmy i przypisania kont — dostęp superadministratora.</p></div></Teleport>
    <Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" placeholder="Nazwa, NIP, adres…" aria-label="Szukaj firmy" /></div></Teleport>
    <nav class="page-menu" aria-label="Menu katalogu firm"><button class="primary" :disabled="busy" @click="edit()"><Plus :size="17" /> Dodaj firmę</button><button :disabled="busy" @click="run(load)"><RefreshCw :size="17" /> Odśwież</button></nav>
    <p class="muted">Każde konto ma jedną firmę. Przypisania zmienisz w module Użytkownicy i grupy. Firmę domyślną możesz nazwać i uzupełnić danymi swojej firmy.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="panel company-table"><table><thead><tr><th>Firma</th><th>NIP</th><th>Kontakt</th><th>Konta</th><th>Akcje</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td><strong>{{ item.name }}</strong><small>{{ item.address }}</small></td><td>{{ item.nip || '—' }}</td><td>{{ item.email || '—' }}<small>{{ item.phone }}</small></td><td>{{ item.user_count }}</td><td class="actions"><button class="icon-button" :disabled="busy" :aria-label="`Edytuj firmę: ${item.name}`" @click="edit(item)"><Pencil :size="17" /></button><button class="icon-button delete-button" :disabled="busy || item.user_count > 0 || item.id === 'default-company'" :aria-label="`Usuń firmę: ${item.name}`" @click="remove(item)"><Trash2 :size="17" /></button></td></tr></tbody></table><p v-if="!filtered.length && !busy" class="empty">Brak firm pasujących do wyszukiwania.</p></div>
    <div v-if="draft" class="modal-backdrop" @keydown.esc="!busy && (draft = null)"><section class="panel company-dialog" role="dialog" aria-modal="true" aria-labelledby="company-title"><header class="editor-heading"><h2 id="company-title"><Building2 :size="20" /> {{ draft.id ? 'Edytuj firmę' : 'Dodaj firmę' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij formularz firmy" @click="draft = null"><X :size="20" /></button></header><form @submit.prevent="save"><p v-if="error" class="error" role="alert">{{ error }}</p><label>Nazwa firmy<input v-model="draft.name" required maxlength="200" autofocus :disabled="busy" /></label><label>NIP (opcjonalnie)<input v-model="draft.nip" maxlength="20" :disabled="busy" /></label><label>Adres<input v-model="draft.address" maxlength="500" :disabled="busy" /></label><label>E-mail kontaktowy<input v-model="draft.email" type="email" maxlength="254" :disabled="busy" /></label><label>Telefon<input v-model="draft.phone" maxlength="50" :disabled="busy" /></label><footer class="editor-actions"><button type="button" :disabled="busy" @click="draft = null">Anuluj</button><button class="primary" :disabled="busy || !draft.name.trim()"><Save :size="17" /> Zapisz firmę</button></footer></form></section></div>
  </section>
</template>
<style scoped>
.company-table { overflow-x:auto; } table { width:100%; border-collapse:collapse; font-size:13px; } th,td { text-align:left; padding:16px; border-bottom:1px solid var(--border); } th { color:var(--muted); background:var(--surface-soft); } td { overflow-wrap:anywhere; } small { display:block; color:var(--muted); margin-top:7px; } .actions { white-space:nowrap; } .company-dialog { width:min(600px,100%); max-height:90dvh; overflow-y:auto; padding:24px; } h2 { display:flex; align-items:center; gap:10px; margin:0; } .muted { font-size:12px; }
</style>
