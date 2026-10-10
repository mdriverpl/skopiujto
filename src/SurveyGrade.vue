<script setup>
defineProps({ grade: Object })
</script>

<template>
  <section v-if="grade" class="survey-grade" aria-label="Ocena ankiety">
    <h3>Ocena ankiety</h3><strong class="grade-value">{{ grade.value }}</strong>
    <p><b>Skala:</b> {{ grade.scale }}</p><p><b>Kryteria z promptu:</b> {{ grade.criteria }}</p>
    <p class="grade-justification"><b>Uzasadnienie:</b> {{ grade.justification }}</p>
  </section>
</template>

<style scoped>
.survey-grade { border-top:1px solid var(--border); margin-top:24px; padding-top:20px; }
h3 { font-size:16px; margin:0 0 14px; }.grade-value { display:inline-block; font-size:24px; color:var(--accent); background:var(--accent-soft); padding:10px 16px; border-radius:12px; }
p { font-size:13px; line-height:1.8; overflow-wrap:anywhere; }.grade-justification { white-space:pre-wrap; }
</style>
