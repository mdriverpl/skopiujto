<script setup>
import { computed, ref, watch } from 'vue'
import { BookOpen, Search, ArrowRight, ExternalLink } from 'lucide-vue-next'
import { findHelpTopics } from './helpContent.js'
const props = defineProps({ user: Object, initialTopic: String })
const emit = defineEmits(['navigate'])
const search = ref(''), selected = ref('help')
const topics = computed(() => findHelpTopics(search.value, props.user?.role, props.user?.is_superadmin))
const topic = computed(() => topics.value.find(item => item.id === selected.value) || topics.value[0])
const moduleIds = ['start', 'ai', 'mail', 'edelivery', 'tasks', 'calendar', 'notes', 'documents', 'surveys', 'drive', 'active', 'templates', 'dictionaries', 'companies', 'admin']
watch(() => props.initialTopic, value => { selected.value = value || 'help'; search.value = '' }, { immediate: true })
</script>

<template>
  <section class="help-page" aria-label="Pomoc i dokumentacja">
    <Teleport to="#workspace-title"><div><h1>Pomoc i dokumentacja</h1><p>Instrukcje modułów, konfiguracja i rozwiązania problemów.</p></div></Teleport>
    <Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" type="search" aria-label="Szukaj w pomocy" placeholder="Szukaj instrukcji, klucza, certyfikatu…" /></div></Teleport>
    <p class="help-intro">Wybierz temat lub wyszukaj problem. Opisy dotyczą funkcji dostępnych w tej wersji aplikacji.</p>
    <div class="help-layout">
      <nav class="panel help-topics" aria-label="Tematy pomocy"><button v-for="item in topics" :key="item.id" :aria-pressed="topic?.id === item.id" @click="selected = item.id"><BookOpen :size="16" aria-hidden="true" /><span>{{ item.title }}</span></button><p v-if="!topics.length" class="help-no-results" role="status">Brak wyników. Zmień wyszukiwanie.</p></nav>
      <article v-if="topic" :key="topic.id" class="panel help-article" aria-labelledby="help-topic-title">
        <header><h2 id="help-topic-title">{{ topic.title }}</h2><p>{{ topic.description }}</p><button v-if="moduleIds.includes(topic.id)" @click="emit('navigate', topic.id)">Otwórz moduł <ArrowRight :size="16" /></button></header>
        <section><h3>Jak korzystać</h3><ol><li v-for="step in topic.steps" :key="step">{{ step }}</li></ol></section>
        <section v-for="part in topic.sections" :key="part.title"><h3>{{ part.title }}</h3><p v-for="paragraph in part.paragraphs" :key="paragraph">{{ paragraph }}</p><ol v-if="part.steps"><li v-for="step in part.steps" :key="step">{{ step }}</li></ol><pre v-if="part.code"><code>{{ part.code }}</code></pre></section>
        <footer v-if="topic.sources"><h3>Oficjalne instrukcje</h3><ul><li v-for="source in topic.sources" :key="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.label }} <ExternalLink :size="13" aria-hidden="true" /><span class="help-sr-only"> (nowa karta)</span></a></li></ul><small>Materiały sprawdzone: {{ topic.verified }}. Przed konfiguracją sprawdź aktualne wymagania operatora.</small></footer>
      </article>
    </div>
  </section>
</template>

<style scoped>
.help-intro { color:var(--muted); font-size:13px; line-height:1.7; margin:0 0 20px; }
.help-layout { display:grid; grid-template-columns:240px minmax(0,1fr); gap:20px; align-items:start; }
.help-topics { padding:10px; display:flex; flex-direction:column; gap:5px; } .help-topics button { justify-content:flex-start; text-align:left; font-size:12px; padding:11px; border:0; background:transparent; line-height:1.5; } .help-topics button svg { flex-shrink:0; color:var(--accent); } .help-topics button[aria-pressed='true'] { color:var(--accent); background:var(--accent-soft); font-weight:600; }
.help-article { padding:28px; min-width:0; overflow-wrap:anywhere; } header { padding-bottom:22px; border-bottom:1px solid var(--border); } h2 { margin:0 0 12px; font-size:23px; } h3 { font-size:15px; margin:24px 0 12px; } p,li { font-size:13px; line-height:1.85; color:var(--secondary); } ol,ul { padding-left:22px; } li + li { margin-top:8px; } header button { font-size:12px; padding:9px 12px; } pre { padding:16px; background:var(--surface-soft); border:1px solid var(--border); border-radius:10px; overflow-x:auto; font-size:12px; line-height:1.8; } code { font-family:Consolas,monospace; } footer { border-top:1px solid var(--border); margin-top:24px; } footer a { display:inline; } footer svg { vertical-align:middle; } footer small { color:var(--muted); font-size:11px; line-height:1.7; } .help-no-results { padding:12px; } .help-sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
@media(max-width:750px) { .help-layout { grid-template-columns:1fr; } .help-topics { flex-direction:row; overflow-x:auto; max-width:100%; } .help-topics button { flex:0 0 auto; white-space:nowrap; } .help-article { padding:20px; } }
</style>
