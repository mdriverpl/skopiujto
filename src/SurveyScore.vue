<script setup>
defineProps({ result: Object })
</script>
<template>
  <section v-if="result" class="survey-score" aria-label="Wynik PHQ-9" role="status">
    <h2>Wynik PHQ-9</h2><strong>{{ result.total }} / {{ result.maximum }} pkt</strong><p>{{ result.severity }}</p><p class="note">{{ result.note }}</p>
    <div class="score-items"><table><thead><tr><th>Pytanie</th><th>Odpowiedź</th><th>Punkty</th></tr></thead><tbody><tr v-for="(item, index) in result.items" :key="item.id"><th scope="row">{{ index + 1 }}. {{ item.label }}</th><td>{{ item.answer }}</td><td>{{ item.points }} / 3</td></tr></tbody></table></div>
    <p v-if="result.follow_up_required" class="follow-up">Odpowiedź na pytanie 9 wskazuje na potrzebę pilnej rozmowy z lekarzem lub specjalistą zdrowia psychicznego, niezależnie od sumy punktów. W razie bezpośredniego zagrożenia życia wezwij pomoc ratunkową.</p>
  </section>
</template>
<style scoped>
.survey-score { margin:20px 0; padding:20px; border:1px solid var(--border); border-radius:14px; background:var(--surface-soft); }h2 { font-size:17px; margin:0 0 12px; }strong { font-size:26px; color:var(--accent); }p { font-size:13px; line-height:1.8; }.note { color:var(--muted); }.follow-up { background:var(--danger-soft); color:var(--danger); padding:14px; border-radius:8px; }
.score-items { overflow-x:auto; }table { width:100%; border-collapse:collapse; font-size:12px; }th,td { padding:10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; }tbody th { font-weight:400; min-width:180px; }td:last-child { white-space:nowrap; }
</style>
