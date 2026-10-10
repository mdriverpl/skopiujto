<script setup>
import BrandMark from './BrandMark.vue'
</script>
<template>
  <div class="brand space-flow-brand" aria-label="Space & Flow">
    <BrandMark class="space-flow-mark" />
    <span class="space-flow-wordmark">
      <span class="space-flow-title" role="img" aria-label="Space & Flow">
        <span class="space-flow-word space-flow-word-space" aria-hidden="true">Space</span>
        <span class="space-flow-amp" aria-hidden="true">&</span>
        <span class="space-flow-word space-flow-word-flow" aria-hidden="true">Flow</span>
      </span>
    </span>
  </div>
</template>

<style>
/* Basic uses the original Forest & Sand stylesheet without color overrides. */
.brand.space-flow-brand { --brand-motion-duration: 16s; gap: 10px; letter-spacing: -.7px; }
.brand.space-flow-brand > .space-flow-mark { width: 40px; height: 40px; flex-shrink: 0; padding: 0; border-radius: 0; background: transparent; color: var(--accent); }
.space-flow-rotor { transform-box: view-box; transform-origin: 24px 24px; animation: space-flow-spin 12s linear infinite; }
@keyframes space-flow-spin { to { transform: rotate(360deg); } }
.space-flow-brand .space-flow-rotor { animation: space-flow-puff var(--brand-motion-duration) ease-in-out infinite; }
@keyframes space-flow-puff {
  0%, 24% { transform: rotate(0deg); }
  50%, 74% { transform: rotate(720deg); }
  100% { transform: rotate(1440deg); }
}
@media (prefers-reduced-motion: reduce) { .space-flow-rotor { animation: none; } }
.space-flow-wordmark { font-size: 18px; font-weight: 650; white-space: nowrap; line-height: 1.2; }
.space-flow-title { position: relative; display: inline-grid; grid-template-columns: 2.8em .9em 2.8em; align-items: center; }
.space-flow-title::before, .space-flow-title::after { content: ''; position: absolute; left: -.4em; bottom: -.25em; width: 1.8em; height: 1px; background: currentColor; opacity: 0; pointer-events: none; animation: space-flow-gust var(--brand-motion-duration) linear infinite; }
.space-flow-title::after { bottom: -.55em; width: 1em; animation-delay: .15s; }
.space-flow-title > .space-flow-amp { grid-area: 1 / 2; text-align: center; }
.space-flow-word { grid-area: 1 / 1; text-align: center; transform-origin: center bottom; }
.space-flow-word-space { animation: space-flow-swap-space var(--brand-motion-duration) ease-in-out infinite; }
.space-flow-word-flow { transform: translateX(3.7em); animation: space-flow-swap-flow var(--brand-motion-duration) ease-in-out infinite; }
@keyframes space-flow-swap-space {
  0%, 26%, 100% { transform: translateX(0); opacity: 1; }
  35% { transform: translateX(1.85em); opacity: .15; }
  45%, 80% { transform: translateX(3.7em); opacity: 1; }
  89% { transform: translateX(1.85em); opacity: .15; }
  99% { transform: translateX(0); opacity: 1; }
}
@keyframes space-flow-swap-flow {
  0%, 30%, 100% { transform: translateX(3.7em); opacity: 1; }
  39% { transform: translateX(1.85em); opacity: .15; }
  49%, 76% { transform: translateX(0); opacity: 1; }
  85% { transform: translateX(1.85em); opacity: .15; }
  95% { transform: translateX(3.7em); opacity: 1; }
}
@keyframes space-flow-gust {
  0%, 26%, 50%, 76%, 100% { transform: translateX(0) scaleX(.4); opacity: 0; }
  30%, 80% { opacity: .25; }
  44%, 94% { transform: translateX(5em) scaleX(1.4); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) { .space-flow-brand .space-flow-rotor, .space-flow-word, .space-flow-title::before, .space-flow-title::after { animation: none; } }
.space-flow-amp { font-family: Georgia, serif; font-style: italic; font-weight: 400; color: var(--accent); }

@media (max-width: 640px) {
  .brand.space-flow-brand { gap: 5px; }
  .brand.space-flow-brand > .space-flow-mark { width: 28px; height: 28px; }
  .space-flow-brand .space-flow-wordmark { font-size: 14px; }
}
@media (max-width: 380px) {
  .brand.space-flow-brand > .space-flow-mark { width: 24px; height: 24px; }
  .space-flow-brand .space-flow-wordmark { font-size: 11px; }
  .has-workspace .account-menu > button { max-width: 70px; }
  .has-workspace .account-menu > button > svg { display: none; }
}

</style>
