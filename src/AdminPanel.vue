<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus, Users, Shield, X, Trash2, Pencil } from 'lucide-vue-next'

const props = defineProps({ api: { type: Function, required: true }, currentUser: { type: Object, required: true } })
const emit = defineEmits(['updated', 'impersonated'])
const accounts = ref([])
const groups = ref([])
const folders = ref([])
const companies = ref([]), groupCompany = ref(props.currentUser.company_id || '')
const groupAccounts = computed(() => accounts.value.filter(account => account.company_id === selectedGroup.value?.company_id))
const groupFolders = computed(() => folders.value.filter(folder => folder.company_id === selectedGroup.value?.company_id))
const busy = ref(false)
const error = ref('')
const notice = ref('')
const activeTab = ref('users')
const sessionHistory = ref([]), historyOpen = ref(false)
const accountForm = ref(null)
const groupName = ref('')
const selectedGroupId = ref('')
const selectedGroup = computed(() => groups.value.find(group => group.id === selectedGroupId.value))
const scope = ref('root')
const grant = ref({ can_read: true, can_edit: false, can_add: false, can_delete: false })
const rights = [{ key: 'can_read', label: 'Odczyt' }, { key: 'can_edit', label: 'Edycja' }, { key: 'can_add', label: 'Dodawanie' }, { key: 'can_delete', label: 'Usuwanie' }]

async function load() {
  const results = await Promise.all([props.api('/admin/users'), props.api('/admin/groups'), props.api('/admin/folders'), props.api(props.currentUser.is_superadmin ? '/admin/companies' : '/me/company')])
  ;[accounts.value, groups.value, folders.value] = results
  companies.value = props.currentUser.is_superadmin ? results[3] : [results[3]]
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
async function enterAccount(account) {
  if (!props.currentUser.is_superadmin || !account.active || account.id === props.currentUser.id || account.is_superadmin) return
  await run(async () => { await props.api(`/admin/users/${account.id}/impersonate`, 'POST'); emit('impersonated') })
}
async function loadSessionHistory() {
  await run(async () => { sessionHistory.value = await props.api('/admin/impersonation/events'); historyOpen.value = true; activeTab.value = 'history' })
}
function editAccount(account) {
  error.value = ''
  accountForm.value = account ? { ...account, email: account.email || '', password: '' } : { name: '', email: '', role: 'user', company_id: props.currentUser.company_id, active: true, can_read: true, can_edit: false, can_add: false, can_delete: false }
}
async function saveAccount() {
  await run(async () => {
    const form = accountForm.value
    const body = { name: form.name, email: form.email, role: form.role, active: form.active, company_id: form.company_id }
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
async function deleteAccount(account) {
  if (busy.value || account.id === props.currentUser.id || account.is_superadmin) return
  if (!window.confirm(`Usunąć użytkownika „${account.name}”? Konto i dostęp zostaną trwale usunięte. Konta z powiązanymi danymi nie można usunąć — można je zablokować.`)) return
  await run(async () => {
    await props.api(`/admin/users/${account.id}`, 'DELETE')
    await load()
    notice.value = 'Usunięto konto użytkownika.'
    emit('updated')
  })
}
async function createGroup() {
  await run(async () => {
    const group = await props.api('/admin/groups', 'POST', { name: groupName.value, company_id: groupCompany.value })
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
watch(selectedGroup, () => { if (scope.value !== 'root' && !groupFolders.value.some(folder => folder.id === scope.value)) scope.value = 'root' })
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
  if (!id) return 'Cały dysk firmy'
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
  <section class="admin-page">
    <Teleport to="#workspace-title"><div><h1>Użytkownicy i grupy</h1><p class="admin-subtitle">Zarządzaj kontami, zespołami i dostępem do dokumentów.</p></div></Teleport>
    <nav class="admin-toolbar" aria-label="Sekcje administracji">
      <div class="admin-tabs" role="group" aria-label="Widok administracji">
        <button :aria-pressed="activeTab === 'users'" @click="activeTab = 'users'"><Users :size="17" /> Użytkownicy <span>{{ accounts.length }}</span></button>
        <button :aria-pressed="activeTab === 'groups'" @click="activeTab = 'groups'"><Shield :size="17" /> Grupy i dostęp <span>{{ groups.length }}</span></button>
        <button v-if="currentUser.is_superadmin" :aria-pressed="activeTab === 'history'" :disabled="busy" @click="loadSessionHistory">Historia wejść</button>
      </div>
      <button v-if="activeTab === 'users'" class="primary" :disabled="busy" @click="editAccount()"><Plus :size="17" /> Dodaj użytkownika</button>
    </nav>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="success" role="status">{{ notice }}</p>

    <section v-if="activeTab === 'history' && historyOpen" class="panel admin-section">
      <div class="admin-section-heading"><div><h2>Historia wejść na konta</h2><p>Aktywność administratorów na kontach klientów.</p></div></div>
      <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Czas</th><th>Administrator</th><th>Konto klienta</th><th>Firma</th><th>Zdarzenie</th></tr></thead><tbody><tr v-for="entry in sessionHistory" :key="entry.id"><td>{{ new Date(entry.created_at).toLocaleString('pl-PL', { timeZone: 'Europe/Warsaw' }) }}</td><td>{{ entry.actor_name }}</td><td>{{ entry.target_name }}</td><td>{{ entry.company_name }}</td><td>{{ entry.action }}</td></tr></tbody></table><p v-if="!sessionHistory.length" class="admin-empty">Brak zapisanych wejść.</p></div>
    </section>

    <section v-if="activeTab === 'users'" class="panel admin-section users-section">
      <div class="admin-section-heading"><div><h2>Konta użytkowników</h2><p>Role, status konta i uprawnienia do własnych zasobów.</p></div></div>
      <div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Użytkownik</th><th>Firma</th><th>Rola</th><th>Status</th><th>Uprawnienia</th><th class="user-actions-heading">Akcje</th></tr></thead><tbody>
        <tr v-for="account in accounts" :key="account.id"><td><strong>{{ account.name }}</strong><small v-if="account.email" class="account-email">{{ account.email }}</small></td><td>{{ account.company_name }}</td><td>{{ account.is_superadmin ? 'Superadministrator' : account.role === 'admin' ? 'Administrator' : 'Użytkownik' }}</td><td><span class="badge" :class="{ ready: account.active }">{{ account.active ? 'Aktywny' : 'Zablokowany' }}</span></td><td><div class="account-rights"><span v-for="right in rights.filter(right => account[right.key])" :key="right.key" class="permission-tag">{{ right.label }}</span></div></td><td><div class="user-actions"><button v-if="currentUser.is_superadmin && account.id !== currentUser.id && !account.is_superadmin" :disabled="busy || !account.active" @click="enterAccount(account)">Wejdź na konto</button><button class="icon-button" :disabled="busy || (account.is_superadmin && !currentUser.is_superadmin)" :aria-label="`Edytuj użytkownika ${account.name}`" title="Edytuj użytkownika" @click="editAccount(account)"><Pencil :size="17" /></button><button v-if="account.id !== currentUser.id && !account.is_superadmin" class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń użytkownika ${account.name}`" title="Usuń użytkownika" @click="deleteAccount(account)"><Trash2 :size="17" /></button></div></td></tr>
      </tbody></table><p v-if="!accounts.length" class="admin-empty">Brak użytkowników.</p></div>
      <p class="admin-footnote">Uprawnienia konta dotyczą własnych zasobów. Dostęp do wspólnych folderów nadaj przez grupy. Zablokowanie konta natychmiast kończy jego sesje.</p>
    </section>

    <section v-if="activeTab === 'groups'" class="panel admin-section groups-section">
      <div class="admin-section-heading"><div><h2>Grupy i dostęp</h2><p>Utwórz grupę, dodaj osoby i określ dostęp do dokumentów.</p></div></div>
      <form class="group-create" :class="{ 'with-company': currentUser.is_superadmin }" @submit.prevent="createGroup">
        <label v-if="currentUser.is_superadmin">Firma<select v-model="groupCompany" required :disabled="busy"><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }}</option></select></label>
        <label>Nazwa nowej grupy<input v-model="groupName" required maxlength="80" :disabled="busy" placeholder="np. Księgowość" /></label>
        <button type="submit" :disabled="busy || !groupName.trim()"><Plus :size="17" /> Utwórz grupę</button>
      </form>
      <div v-if="groups.length" class="group-selection">
        <label>Wybrana grupa<select v-model="selectedGroupId" :disabled="busy"><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}{{ currentUser.is_superadmin ? ' · ' + (companies.find(company => company.id === group.company_id)?.name || '') : '' }}</option></select></label>
        <button class="delete-button" :disabled="busy" @click="deleteGroup"><Trash2 :size="16" /> Usuń grupę</button>
      </div>
      <p v-else class="admin-empty">Nie masz jeszcze grup. Utwórz pierwszą grupę powyżej.</p>
      <div v-if="selectedGroup" class="group-columns">
        <section class="group-card members-card" aria-labelledby="group-members-title">
          <div class="group-card-heading"><span class="section-icon"><Users :size="19" /></span><div><h3 id="group-members-title">Członkowie grupy <span>{{ selectedGroup.members.length }}</span></h3><p>Zaznacz osoby należące do grupy.</p></div></div>
          <div class="member-grid"><label v-for="account in groupAccounts" :key="account.id" class="member-option"><input type="checkbox" :checked="selectedGroup.members.includes(account.id)" :disabled="busy" @change="setMember(account, $event.target.checked)" /><span><strong>{{ account.name }}</strong><small v-if="account.email">{{ account.email }}</small><small v-if="!account.active" class="blocked-member">Konto zablokowane</small></span></label></div>
          <p v-if="!groupAccounts.length" class="admin-empty">Brak użytkowników w tej firmie.</p>
          <p class="card-hint">Zmiany członkostwa zapisują się automatycznie.</p>
        </section>
        <section class="group-card permissions-card" aria-labelledby="group-permissions-title">
          <div class="group-card-heading"><span class="section-icon"><Shield :size="19" /></span><div><h3 id="group-permissions-title">Uprawnienia grupy</h3><p>Wybierz zakres i dozwolone działania.</p></div></div>
          <form class="grant-form" @submit.prevent="saveGrant">
            <label>Zakres dostępu<select v-model="scope" :disabled="busy"><option value="root">Cały dysk firmy</option><option v-for="folder in groupFolders" :key="folder.id" :value="folder.id">{{ scopeName(folder.id) }}</option></select></label>
            <div class="permission-checks"><label v-for="right in rights" :key="right.key" class="permission-option"><input v-model="grant[right.key]" type="checkbox" :disabled="busy" /><span>{{ right.label }}</span></label></div>
            <div class="grant-submit"><button class="primary" type="submit" :disabled="busy">Zapisz uprawnienia</button></div>
          </form>
          <details class="access-rules"><summary>Jak działają uprawnienia?</summary><p>Grupa otrzymuje dostęp do wybranego folderu i podfolderów dziedziczących dostęp. Uprawnienia ze wszystkich grup sumują się. „Cały dysk firmy” obejmuje zasoby użytkowników firmy tej grupy, poza folderami z własnym wyborem odbiorców.</p><p>Edycja, dodawanie lub usuwanie włączają też odczyt. Dokument może edytować tylko jego twórca. Plik może usunąć lub zastąpić wyłącznie osoba, która go dodała. Usuwane foldery muszą być puste.</p></details>
          <div class="saved-grants"><h4>Zapisany dostęp</h4><div class="grant-list"><div v-for="item in selectedGroup.permissions" :key="item.scope" class="grant-row"><div><strong>{{ scopeName(item.folder_id) }}</strong><div><span v-for="right in rights.filter(right => item[right.key])" :key="right.key" class="permission-tag">{{ right.label }}</span></div></div><button class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń uprawnienia do ${scopeName(item.folder_id)}`" @click="revokeGrant(item)"><Trash2 :size="17" /></button></div></div><p v-if="!selectedGroup.permissions.length" class="card-hint">Brak nadanych uprawnień. Wybierz zakres i zapisz dostęp.</p></div>
        </section>
      </div>
    </section>
  </section>
  <div v-if="accountForm" class="modal-backdrop"><section class="panel editor" role="dialog" aria-modal="true" aria-labelledby="account-title"><div class="editor-heading"><h2 id="account-title">{{ accountForm.id ? 'Edytuj użytkownika' : 'Nowy użytkownik' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="accountForm = null"><X :size="21" /></button></div><p v-if="error" class="error" role="alert">{{ error }}</p>
    <form @submit.prevent="saveAccount">
      <label>Nazwa użytkownika<input v-model="accountForm.name" required minlength="2" maxlength="80" autocomplete="off" /></label>
      <label>Firma<select v-model="accountForm.company_id" required :disabled="busy || !currentUser.is_superadmin"><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }}</option></select></label>
      <p v-if="currentUser.is_superadmin && accountForm.id" class="muted">Zmiana firmy usuwa członkostwa w grupach i kończy sesje użytkownika. Jego dokumenty pozostają przypisane do konta.</p>
      <label>Adres e-mail<input v-model="accountForm.email" type="email" :required="!accountForm.id" maxlength="254" autocomplete="email" /></label>
      <p v-if="!accountForm.id" class="muted">Wyślemy na ten adres wygenerowane hasło tymczasowe. Przy pierwszym logowaniu użytkownik ustawi własne hasło.</p>
      <label v-if="accountForm.id">Nowe hasło tymczasowe (pozostaw puste, aby zachować obecne)<input v-model="accountForm.password" type="password" minlength="10" maxlength="200" autocomplete="new-password" /></label>
      <p v-if="accountForm.id && accountForm.password" class="muted">Przekaż hasło użytkownikowi. Przy kolejnym logowaniu będzie musiał je zmienić.</p>
      <label>Rola<select v-model="accountForm.role" :disabled="accountForm.id === currentUser.id"><option value="user">Użytkownik</option><option value="admin">Administrator</option></select></label><label v-if="accountForm.id" class="check-label"><input v-model="accountForm.active" type="checkbox" :disabled="accountForm.id === currentUser.id" /> Konto aktywne</label><fieldset><legend>Uprawnienia do własnych plików i folderów</legend><div class="permission-checks"><label v-for="right in rights" :key="right.key" class="check-label"><input v-model="accountForm[right.key]" type="checkbox" /> {{ right.label }}</label></div></fieldset><p class="muted">Nowe konto ma domyślnie tylko odczyt. Dostęp do zasobów innych osób nadaj przez grupy.</p><div class="editor-actions"><button type="button" :disabled="busy" @click="accountForm = null">Anuluj</button><button class="primary" type="submit" :disabled="busy">Zapisz użytkownika</button></div>
    </form>
  </section></div>
</template>

<style scoped>
.admin-page { display:grid; gap:20px; min-width:0; }
h1 { margin:0 0 8px; font-size:25px; }
.admin-subtitle { margin:0; color:var(--muted); font-size:12px; line-height:1.6; }
.admin-toolbar { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:14px; }
.admin-tabs { display:flex; gap:5px; flex-wrap:wrap; padding:5px; background:var(--surface-soft); border:1px solid var(--border); border-radius:12px; }
.admin-tabs button { border:0; background:transparent; padding:10px 14px; color:var(--muted); font-size:12px; }
.admin-tabs button[aria-pressed='true'] { color:var(--accent); background:var(--surface); box-shadow:0 1px 5px #0000000a; font-weight:600; }
.admin-tabs button span { font-size:10px; padding:2px 6px; border-radius:5px; background:var(--accent-soft); color:var(--accent); }
.admin-section { margin:0; padding:24px; min-width:0; }
.admin-section-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:22px; }
.admin-section-heading h2 { margin:0; font-size:17px; }
.admin-section-heading p { margin:7px 0 0; font-size:12px; line-height:1.6; color:var(--muted); }
.admin-footnote { margin:18px 0 0; font-size:11px; line-height:1.7; color:var(--muted); }
.admin-table { min-width:760px; }
.admin-table th { background:var(--surface-soft); font-size:11px; }
.admin-table td { padding-top:17px; padding-bottom:17px; font-size:12px; }
.admin-table tbody tr:last-child td { border-bottom:0; }
.account-email { display:block; margin-top:5px; color:var(--muted); font-size:11px; }
.account-rights { display:flex; flex-wrap:wrap; gap:4px; min-width:130px; }
.account-rights .permission-tag { margin:0; }
.user-actions { display:flex; align-items:center; justify-content:flex-end; gap:3px; }
.user-actions button { white-space:nowrap; font-size:11px; }
.user-actions-heading { text-align:right; }
.group-create { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:14px; padding:18px; background:var(--surface-soft); border:1px solid var(--border); border-radius:12px; margin:0 0 22px; }
.group-create.with-company { grid-template-columns:minmax(160px,.7fr) minmax(180px,1fr) auto; }
.group-create button { min-height:42px; white-space:nowrap; }
.group-create label,.group-selection label,.grant-form label { min-width:0; font-size:12px; }
.group-create select,.group-selection select,.grant-form select { width:100%; min-height:42px; font-size:12px; }
.group-create input { font-size:12px; min-height:42px; }
.group-selection { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:end; margin:0 0 24px; padding-bottom:24px; border-bottom:1px solid var(--border); }
.group-selection button { min-height:42px; font-size:12px; }
.delete-button { color:var(--theme-danger,#ba253b); }
.group-columns { display:grid; grid-template-columns:minmax(250px,.8fr) minmax(0,1.2fr); gap:20px; align-items:start; }
.group-card { padding:20px; border:1px solid var(--border); border-radius:12px; min-width:0; }
.group-card-heading { display:flex; align-items:flex-start; gap:12px; margin-bottom:20px; }
.section-icon { display:flex; flex-shrink:0; padding:9px; border-radius:10px; color:var(--accent); background:var(--accent-soft); }
.group-card-heading h3 { margin:2px 0 6px; font-size:14px; line-height:1.5; }
.group-card-heading h3 > span { font-size:11px; margin-left:5px; color:var(--muted); }
.group-card-heading p { margin:0; color:var(--muted); font-size:11px; line-height:1.6; }
.member-grid { display:grid; grid-template-columns:1fr; gap:8px; padding:0; border:0; }
.member-option { display:flex; flex-direction:row; align-items:flex-start; gap:11px; padding:12px; background:var(--surface-soft); border:1px solid transparent; border-radius:9px; cursor:pointer; }
.member-option:has(input:checked) { border-color:var(--border); background:var(--accent-soft); }
.member-option > input,.permission-option > input { width:16px; height:16px; margin:1px 0 0; flex-shrink:0; accent-color:var(--accent); }
.member-option > span { min-width:0; overflow-wrap:anywhere; }
.member-option strong { font-weight:500; font-size:12px; }
.member-option small { display:block; font-size:10px; margin-top:4px; color:var(--muted); line-height:1.5; }
.member-option .blocked-member { color:var(--theme-danger,#ba253b); }
.grant-form { display:flex; flex-direction:column; gap:18px; }
.permission-checks { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.permission-option { display:flex; flex-direction:row; gap:10px; align-items:center; padding:12px 10px; border:1px solid var(--border); border-radius:9px; font-size:12px; cursor:pointer; }
.permission-option:has(input:checked) { background:var(--accent-soft); }
.grant-submit { display:flex; justify-content:flex-end; }
.grant-submit button { font-size:12px; }
.access-rules { margin-top:18px; color:var(--muted); font-size:11px; line-height:1.7; }
.access-rules summary { cursor:pointer; color:var(--secondary); }
.access-rules p { margin:10px 0; }
.saved-grants { border-top:1px solid var(--border); padding-top:18px; margin-top:20px; }
.saved-grants h4 { font-size:12px; font-weight:600; margin:0 0 10px; }
.grant-list { margin:0; }
.grant-row { padding:12px 0; font-size:12px; }
.grant-row:first-child { border-top:0; }
.grant-row > div { min-width:0; overflow-wrap:anywhere; }
.grant-row strong { font-weight:500; }
.card-hint { margin:14px 0 0; font-size:10px; line-height:1.7; color:var(--muted); }
.admin-empty { padding:18px 0; text-align:center; font-size:12px; line-height:1.7; color:var(--muted); }
@media(max-width:1200px) { .group-columns { grid-template-columns:1fr; }.member-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:700px) { .admin-section { padding:18px; }.group-create.with-company,.group-create { grid-template-columns:1fr; }.group-create button { justify-self:start; }.group-selection { grid-template-columns:1fr; }.group-selection button { justify-self:start; }.member-grid { grid-template-columns:1fr; }.group-card { padding:16px; }.admin-tabs { width:100%; }.admin-tabs button { flex:1; padding:10px; }.admin-toolbar > .primary { width:100%; }.grant-submit button { width:100%; } }
</style>
