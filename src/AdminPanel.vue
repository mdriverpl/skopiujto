<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus, Users, Shield, X, Trash2, Pencil } from 'lucide-vue-next'

const props = defineProps({ api: { type: Function, required: true }, currentUser: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const accounts = ref([])
const groups = ref([])
const folders = ref([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const accountForm = ref(null)
const groupName = ref('')
const selectedGroupId = ref('')
const selectedGroup = computed(() => groups.value.find(group => group.id === selectedGroupId.value))
const scope = ref('root')
const grant = ref({ can_read: true, can_edit: false, can_add: false, can_delete: false })
const rights = [{ key: 'can_read', label: 'Odczyt' }, { key: 'can_edit', label: 'Edycja' }, { key: 'can_add', label: 'Dodawanie' }, { key: 'can_delete', label: 'Usuwanie' }]

async function load() {
  const results = await Promise.all([props.api('/admin/users'), props.api('/admin/groups'), props.api('/admin/folders')])
  ;[accounts.value, groups.value, folders.value] = results
  if (!selectedGroup.value) selectedGroupId.value = groups.value[0]?.id || ''
}
async function run(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try { await action() } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function editAccount(account) {
  error.value = ''
  accountForm.value = account ? { ...account, email: account.email || '', password: '' } : { name: '', email: '', role: 'user', active: true, can_read: true, can_edit: false, can_add: false, can_delete: false }
}
async function saveAccount() {
  await run(async () => {
    const form = accountForm.value
    const body = { name: form.name, email: form.email, role: form.role, active: form.active }
    for (const right of rights) body[right.key] = form[right.key]
    if (form.password) body.password = form.password
    await props.api(form.id ? `/admin/users/${form.id}` : '/admin/users', form.id ? 'PATCH' : 'POST', body)
    accountForm.value = null
    if (form.id === props.currentUser.id && form.password) {
      emit('updated')
      return
    }
    await load()
    notice.value = form.id ? 'Zapisano konto użytkownika.' : 'Utworzono konto i wysłano e-mail z hasłem tymczasowym.'
    emit('updated')
  })
}
async function createGroup() {
  await run(async () => {
    const group = await props.api('/admin/groups', 'POST', { name: groupName.value })
    groupName.value = ''
    selectedGroupId.value = group.id
    await load()
  })
}
async function deleteGroup() {
  const group = selectedGroup.value
  if (!group || !window.confirm(`Usunąć grupę „${group.name}” i jej uprawnienia? Pliki pozostaną na dysku.`)) return
  await run(async () => {
    await props.api(`/admin/groups/${group.id}`, 'DELETE')
    await load()
    emit('updated')
  })
}
async function setMember(account, checked) {
  await run(async () => {
    await props.api(`/admin/groups/${selectedGroupId.value}/members/${account.id}`, checked ? 'PUT' : 'DELETE')
    await load()
    emit('updated')
  })
}
function updateGrantForm() {
  const existing = selectedGroup.value?.permissions.find(item => item.scope === scope.value)
  grant.value = Object.fromEntries(rights.map(right => [right.key, existing ? !!existing[right.key] : right.key === 'can_read']))
}
watch([selectedGroup, scope], updateGrantForm)
async function saveGrant() {
  await run(async () => {
    await props.api(`/admin/groups/${selectedGroupId.value}/permissions`, 'PUT', { folder_id: scope.value === 'root' ? null : scope.value, ...grant.value })
    await load()
    notice.value = 'Zapisano uprawnienia grupy.'
    emit('updated')
  })
}
async function revokeGrant(item) {
  await run(async () => {
    await props.api(`/admin/groups/${selectedGroupId.value}/permissions`, 'PUT', { folder_id: item.folder_id, can_read: false, can_edit: false, can_add: false, can_delete: false })
    await load()
    emit('updated')
  })
}
function scopeName(id) {
  if (!id) return 'Cały dysk'
  const path = []
  let folder = folders.value.find(item => item.id === id)
  const owner = folder?.owner_name
  while (folder) {
    path.unshift(folder.name)
    folder = folders.value.find(item => item.id === folder.parent_id)
  }
  return `${owner || ''}: ${path.join(' / ')}`
}
onMounted(() => run(load))
</script>

<template>
  <section class="page-heading"><div><span class="eyebrow">Administracja</span><h1>Użytkownicy i uprawnienia</h1><p class="muted">Zarządzaj kontami i dostępem grup do dokumentów.</p></div><button class="primary" :disabled="busy" @click="editAccount()"><Plus :size="18" /> Dodaj użytkownika</button></section>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="notice" class="success" role="status">{{ notice }}</p>
  <section class="panel admin-section">
    <h2><Users :size="20" /> Użytkownicy</h2>
    <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Nazwa</th><th>Rola</th><th>Status</th><th>Własne pliki i foldery</th><th></th></tr></thead><tbody>
      <tr v-for="account in accounts" :key="account.id"><td><strong>{{ account.name }}</strong></td><td>{{ account.role === 'admin' ? 'Administrator' : 'Użytkownik' }}</td><td><span class="badge" :class="{ ready: account.active }">{{ account.active ? 'Aktywny' : 'Zablokowany' }}</span></td><td><span v-for="right in rights.filter(right => account[right.key])" :key="right.key" class="permission-tag">{{ right.label }}</span></td><td><button class="icon-button" :disabled="busy" :aria-label="`Edytuj użytkownika ${account.name}`" @click="editAccount(account)"><Pencil :size="18" /></button></td></tr>
    </tbody></table></div>
    <p class="muted">Uprawnienia konta dotyczą własnych zasobów. Dostęp do wspólnych folderów nadaj przez grupy. Zablokowanie konta natychmiast kończy jego sesje.</p>
  </section>
  <section class="panel admin-section">
    <h2><Shield :size="20" /> Grupy i dostęp</h2>
    <form class="inline-form" @submit.prevent="createGroup"><label class="grow">Nazwa nowej grupy<input v-model="groupName" required maxlength="80" placeholder="np. Księgowość" /></label><button :disabled="busy || !groupName.trim()" type="submit"><Plus :size="17" /> Utwórz grupę</button></form>
    <div v-if="groups.length" class="group-selection"><label class="grow">Wybrana grupa<select v-model="selectedGroupId" :disabled="busy"><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option></select></label><button class="delete-button" :disabled="busy" @click="deleteGroup"><Trash2 :size="17" /> Usuń grupę</button></div>
    <p v-else class="muted">Utwórz grupę, aby przypisać użytkowników i uprawnienia.</p>
    <template v-if="selectedGroup">
      <h3>Członkowie grupy</h3><div class="member-grid"><label v-for="account in accounts" :key="account.id" class="check-label"><input type="checkbox" :checked="selectedGroup.members.includes(account.id)" :disabled="busy" @change="setMember(account, $event.target.checked)" /> {{ account.name }}{{ account.active ? '' : ' (zablokowany)' }}</label></div>
      <h3>Uprawnienia do dysku lub folderu</h3>
      <p class="muted">Grupa otrzymuje dostęp do wybranego folderu i podfolderów dziedziczących dostęp. Uprawnienia ze wszystkich grup sumują się. „Cały dysk” obejmuje zasoby wszystkich użytkowników, poza folderami z własnym wyborem odbiorców.</p>
      <form @submit.prevent="saveGrant"><label>Zakres<select v-model="scope" :disabled="busy"><option value="root">Cały dysk</option><option v-for="folder in folders" :key="folder.id" :value="folder.id">{{ scopeName(folder.id) }}</option></select></label><div class="permission-checks"><label v-for="right in rights" :key="right.key" class="check-label"><input v-model="grant[right.key]" type="checkbox" :disabled="busy" /> {{ right.label }}</label></div><div><button class="primary" type="submit" :disabled="busy">Zapisz uprawnienia</button></div></form>
      <p class="muted">Edycja, dodawanie lub usuwanie włączają też odczyt. Dokument może edytować tylko jego twórca, również przy uprawnieniach grupowych. Plik może usunąć lub zastąpić wyłącznie osoba, która go dodała. Usuwane foldery muszą być puste.</p>
      <div class="grant-list"><div v-for="item in selectedGroup.permissions" :key="item.scope" class="grant-row"><div><strong>{{ scopeName(item.folder_id) }}</strong><div><span v-for="right in rights.filter(right => item[right.key])" :key="right.key" class="permission-tag">{{ right.label }}</span></div></div><button class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń uprawnienia do ${scopeName(item.folder_id)}`" @click="revokeGrant(item)"><Trash2 :size="18" /></button></div></div>
    </template>
  </section>
  <div v-if="accountForm" class="modal-backdrop"><section class="panel editor" role="dialog" aria-modal="true" aria-labelledby="account-title"><div class="editor-heading"><h2 id="account-title">{{ accountForm.id ? 'Edytuj użytkownika' : 'Nowy użytkownik' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="accountForm = null"><X :size="21" /></button></div><p v-if="error" class="error" role="alert">{{ error }}</p>
    <form @submit.prevent="saveAccount">
      <label>Nazwa użytkownika<input v-model="accountForm.name" required minlength="2" maxlength="80" autocomplete="off" /></label>
      <label>Adres e-mail<input v-model="accountForm.email" type="email" :required="!accountForm.id" maxlength="254" autocomplete="email" /></label>
      <p v-if="!accountForm.id" class="muted">Wyślemy na ten adres wygenerowane hasło tymczasowe. Przy pierwszym logowaniu użytkownik ustawi własne hasło.</p>
      <label v-if="accountForm.id">Nowe hasło tymczasowe (pozostaw puste, aby zachować obecne)<input v-model="accountForm.password" type="password" minlength="10" maxlength="200" autocomplete="new-password" /></label>
      <p v-if="accountForm.id && accountForm.password" class="muted">Przekaż hasło użytkownikowi. Przy kolejnym logowaniu będzie musiał je zmienić.</p>
      <label>Rola<select v-model="accountForm.role" :disabled="accountForm.id === currentUser.id"><option value="user">Użytkownik</option><option value="admin">Administrator</option></select></label><label v-if="accountForm.id" class="check-label"><input v-model="accountForm.active" type="checkbox" :disabled="accountForm.id === currentUser.id" /> Konto aktywne</label><fieldset><legend>Uprawnienia do własnych plików i folderów</legend><div class="permission-checks"><label v-for="right in rights" :key="right.key" class="check-label"><input v-model="accountForm[right.key]" type="checkbox" /> {{ right.label }}</label></div></fieldset><p class="muted">Nowe konto ma domyślnie tylko odczyt. Dostęp do zasobów innych osób nadaj przez grupy.</p><div class="editor-actions"><button type="button" :disabled="busy" @click="accountForm = null">Anuluj</button><button class="primary" type="submit" :disabled="busy">Zapisz użytkownika</button></div>
    </form>
  </section></div>
</template>
