<script setup>
import { computed, ref } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import SurveyGrade from './SurveyGrade.vue'

const props = defineProps({ api: Function, surveys: { type: Array, default: () => [] } })
const emit = defineEmits(['busy'])
const selectedIds = ref([]), prompt = ref(''), busy = ref(false), error = ref(''), report = ref(null)
const grading = ref(false)
const owned = computed(() => props.surveys.filter(item => item.is_owner))
const eligible = computed(() => owned.value.filter(item => item.completed > 0))
const sections = computed(() => report.value ? [
  ...report.value.surveys.map((item, index) => ({ ...item, heading: `${index + 1}. ${item.title}` })),
  { ...report.value.summary, id: 'combined-summary', heading: 'Podsumowanie wszystkich ankiet' },
] : [])
function selectAll() { if (!busy.value && eligible.value.length <= 10) selectedIds.value = eligible.value.map(item => item.id) }
async function analyze() {
  if (busy.value || !selectedIds.value.length || selectedIds.value.length > 10) return
  if (grading.value && !prompt.value.trim()) { error.value = 'Podaj w prompcie kryteria i skalę oceny ankiety.'; return }
  const identifiers = selectedIds.value.filter(id => eligible.value.some(item => item.id === id))
  if (identifiers.length !== selectedIds.value.length) { error.value = 'Wybierz ankiety z przesłanymi odpowiedziami.'; return }
  busy.value = true; error.value = ''; emit('busy', true)
  try { report.value = await props.api('/surveys/interpretation', 'POST', { survey_ids: identifiers, prompt: prompt.value.trim(), grading: grading.value }) }
  catch (err) { error.value = err.message }
  finally { busy.value = false; emit('busy', false) }
}
</script>

<template>
  <section class="answers-analysis" :aria-busy="busy">
    <form class="panel analysis-settings" @submit.prevent="analyze">
      <h2>Analiza odpowiedzi</h2>
      <p>Wybierz ankiety. AI przeanalizuje odpowiedzi każdej z nich osobno, a na końcu przygotuje wspólne podsumowanie.</p>
      <div class="analysis-selection"><button type="button" :disabled="busy || !eligible.length || eligible.length > 10" @click="selectAll">Zaznacz wszystkie</button><button type="button" :disabled="busy || !selectedIds.length" @click="selectedIds = []">Wyczyść wybór</button><span>Wybrano {{ selectedIds.length }} / 10</span></div>
      <div class="analysis-surveys"><label v-for="item in owned" :key="item.id"><input v-model="selectedIds" type="checkbox" :value="item.id" :disabled="busy || !item.completed || (selectedIds.length >= 10 && !selectedIds.includes(item.id))" /><span><strong>{{ item.title }}</strong><small>{{ item.completed }} / {{ item.expected }} odpowiedzi<template v-if="!item.completed"> · oczekuje na odpowiedzi</template></small></span></label></div>
      <p v-if="!owned.length">Nie masz jeszcze własnych ankiet do analizy.</p>
      <label class="analysis-prompt">Prompt (opcjonalnie)<textarea v-model="prompt" rows="4" maxlength="8000" :disabled="busy" placeholder="Np. W każdej ankiecie wskaż problemy z obsługą. Na końcu podsumuj wspólne wnioski i zaproponuj działania." /></label>
      <label class="grading-option"><input v-model="grading" type="checkbox" :disabled="busy" /> Ankieta z oceną</label>
      <p v-if="grading" class="muted">Podaj kryteria i skalę w prompcie, np. „Oceń satysfakcję w skali 1–5: 1 oznacza przewagę negatywnych opinii, 5 — przewagę pozytywnych. Uzasadnij ocenę”. Ocena pojawi się na końcu analizy każdej ankiety.</p>
      <p class="muted">Pytania i przesłane odpowiedzi trafią do OpenAI, bez nazw i adresów odbiorców. Treść odpowiedzi może zawierać dane wpisane przez uczestników.</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" class="primary" :disabled="busy || !selectedIds.length || selectedIds.length > 10"><Sparkles :size="16" /> {{ busy ? 'Analizowanie odpowiedzi…' : 'Analizuj wybrane ankiety' }}</button>
      <p v-if="busy" role="status">Trwa osobna analiza wybranych ankiet i przygotowanie podsumowania. Może to potrwać kilka minut.</p>
    </form>
    <div v-if="report" class="analysis-results">
      <p class="muted">Wyniki dla {{ report.surveys.length }} ankiet. Prompt: {{ report.prompt || 'analiza ogólna' }}. Osobne interpretacje zapisano przy ankietach.</p>
      <article v-for="item in sections" :key="item.id" class="panel analysis-report" :class="{ 'analysis-summary': item.id === 'combined-summary' }">
        <h2>{{ item.heading }}</h2>
        <p v-if="item.completed !== undefined" class="muted">Przeanalizowano {{ item.completed }} z {{ item.expected }} oczekiwanych odpowiedzi.</p>
        <p v-if="item.stale" role="status">W trakcie analizy wyniki zmieniły się. Odśwież interpretację tej ankiety.</p>
        <h3>Podsumowanie</h3><p class="report-text">{{ item.summary }}</p>
        <template v-for="(label, key) in { findings: 'Wnioski', recommendations: 'Proponowane działania', limitations: 'Ograniczenia analizy' }" :key="key"><h3>{{ label }}</h3><ul v-if="item[key].length"><li v-for="(text, index) in item[key]" :key="index">{{ text }}</li></ul><p v-else class="muted">Brak dodatkowych propozycji.</p></template>
        <SurveyGrade :grade="item.grade" />
      </article>
    </div>
  </section>
</template>

<style scoped>
.grading-option { display:flex; flex-direction:row; align-items:center; gap:10px; font-size:13px; }.grading-option input { width:16px; height:16px; accent-color:var(--accent); }
.analysis-settings,.analysis-report { padding:26px; border-radius:16px; margin:20px 0; }
h2 { font-size:18px; margin:0 0 12px; }h3 { font-size:14px; margin-top:24px; }
p,li { font-size:13px; line-height:1.8; overflow-wrap:anywhere; }li { margin-bottom:8px; }.muted { color:var(--muted); font-size:12px; }
.analysis-selection { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:16px 0; }.analysis-selection span { font-size:12px; color:var(--muted); }
.analysis-surveys { max-height:320px; overflow-y:auto; border:1px solid var(--border); border-radius:12px; }
.analysis-surveys label { display:flex; flex-direction:row; align-items:center; gap:12px; padding:12px; margin:0; border-bottom:1px solid var(--border); }
.analysis-surveys input { width:16px; height:16px; accent-color:var(--accent); }.analysis-surveys strong { font-size:13px; }.analysis-surveys small { display:block; color:var(--muted); font-size:11px; margin-top:4px; }
.analysis-prompt { margin:20px 0; font-size:12px; }.report-text { white-space:pre-wrap; }.analysis-summary { border-color:var(--accent); }
</style>
