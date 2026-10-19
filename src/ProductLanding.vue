<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ArrowRight, ArrowUpRight, Check, Pause, Play, Menu, X, ShieldCheck } from 'lucide-vue-next'
import BrandLogo from './BrandLogo.vue'
import ProductShowcase from './ProductShowcase.vue'
import FlowShelfAnimation from './FlowShelfAnimation.vue'
import FeatureProcessAnimation from './FeatureProcessAnimation.vue'
import SecurityArchitectureAnimation from './SecurityArchitectureAnimation.vue'
import SurveyProductAnimation from './SurveyProductAnimation.vue'
import AlertProductAnimation from './AlertProductAnimation.vue'
import EdzioAvatar from './EdzioAvatar.vue'
import { productSections, findProductSection } from './productFeatures.js'

defineProps({ error: String })
const paused = ref(false), menuOpen = ref(false)
function readFeature() { return findProductSection(new URL(window.location.href).searchParams.get('feature')).id }
const selectedId = ref(readFeature())
const selectedPage = computed(() => findProductSection(selectedId.value))
const productHeading = ref(null)
async function selectFeature(value) {
  const feature = findProductSection(value)
  selectedId.value = feature.id
  const address = new URL(window.location.href)
  if (feature.id === 'home') address.searchParams.delete('feature')
  else address.searchParams.set('feature', feature.id)
  address.hash = ''
  if (address.href !== window.location.href) window.history.pushState({ feature: feature.id }, '', address.pathname + address.search)
  await nextTick()
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reducedMotion ? 'instant' : 'smooth' })
  productHeading.value?.focus({ preventScroll: true })
}
function restoreFeature() {
  selectedId.value = readFeature()
  window.scrollTo(0, 0)
}
function closeMenu() { menuOpen.value = false }
onMounted(() => window.addEventListener('popstate', restoreFeature))
onBeforeUnmount(() => window.removeEventListener('popstate', restoreFeature))
</script>

<template>
  <div class="product-page">
    <a class="product-skip" href="#produkt">Przejdź do treści</a>
    <header class="product-header">
      <a class="product-brand" href="/" aria-label="Space & Flow — strona główna"><BrandLogo /></a>
      <nav id="product-navigation" aria-label="Menu strony produktu" :class="{ 'is-open': menuOpen }">
        <a href="#wybierz-funkcje" @click="closeMenu">Możliwości</a>
      </nav>
      <a class="product-login-link" href="#logowanie" @click="closeMenu">Zaloguj się <ArrowUpRight :size="16" /></a>
      <button class="product-menu-toggle" :aria-expanded="menuOpen" aria-controls="product-navigation" :aria-label="menuOpen ? 'Zamknij menu produktu' : 'Otwórz menu produktu'" @click="menuOpen = !menuOpen"><X v-if="menuOpen" :size="22" /><Menu v-else :size="22" /></button>
    </header>

    <section id="produkt" class="product-hero product-width" :data-feature="selectedId">
      <div :key="selectedId" class="product-hero-copy feature-copy-enter">
        <button v-if="selectedId !== 'home'" class="product-overview-back" @click="selectFeature('home')">← Wszystkie możliwości</button>
        <span class="product-eyebrow"><span></span>{{ selectedId === 'home' ? 'Twoje zadania, dokumenty i pomysły' : selectedPage.tag }}</span>
        <h1 ref="productHeading" tabindex="-1">{{ selectedPage.heading }}<span>{{ selectedPage.accent }}</span></h1>
        <p>{{ selectedPage.description }}</p>
        <ul v-if="selectedPage.benefits" class="hero-feature-benefits"><li v-for="benefit in selectedPage.benefits" :key="benefit"><span v-if="selectedId === 'security'" class="security-benefit-dot"></span><Check v-else :size="15" />{{ benefit }}</li></ul>
        <div v-if="selectedId === 'security'" class="hero-security-context"><p>{{ selectedPage.deploymentNote }}</p><nav aria-label="Źródła informacji o NIS2"><a href="https://eli.gov.pl/eli/DU/2026/252/ogl" target="_blank" rel="noopener noreferrer">Ustawa KSC ↗</a><a href="https://www.gov.pl/web/cyfryzacja/nowelizacja-ustawy-o-krajowym-systemie-cyberbezpieczenstwa-zaczyna-obowiazywac" target="_blank" rel="noopener noreferrer">Wyjaśnienia Ministerstwa Cyfryzacji ↗</a></nav></div>
        <div class="product-hero-actions"><a class="product-button" href="#logowanie">{{ selectedId === 'home' ? 'Wejdź do swojej przestrzeni' : 'Zaloguj się i zacznij' }}<ArrowRight :size="18" /></a><a class="product-text-link" href="#wybierz-funkcje">Poznaj możliwości <ArrowUpRight :size="17" /></a></div>
        <div v-if="selectedId === 'home'" class="product-hero-note"><span><Check :size="14" /> Prosto. Razem. W dobrym flow.</span><span><Check :size="14" /> Na komputerze i telefonie</span></div>
      </div>
      <div :key="'animation-' + selectedId" class="product-motion product-motion-shelves" :class="{ 'motion-paused': paused, 'feature-light-demo': ['ai','calendar','process','security','surveys','alert'].includes(selectedPage.mode) }">
        <div class="motion-heading"><span class="motion-dot"></span>{{ selectedId === 'home' ? 'Od chaosu do dobrego flow' : selectedPage.name }}<span class="motion-live">SPACE / FLOW</span></div>
        <FlowShelfAnimation v-if="selectedPage.mode === 'shelves'" :mode="selectedId" :paused="paused" />
        <ProductShowcase v-else-if="selectedPage.mode === 'ai' || selectedPage.mode === 'calendar'" compact-hero :initial-tab="selectedPage.mode" :paused="paused" />
        <SecurityArchitectureAnimation v-else-if="selectedPage.mode === 'security'" :paused="paused" />
        <SurveyProductAnimation v-else-if="selectedPage.mode === 'surveys'" :paused="paused" />
        <AlertProductAnimation v-else-if="selectedPage.mode === 'alert'" :paused="paused" />
        <FeatureProcessAnimation v-else :mode="selectedId" :paused="paused" />
        <div class="motion-footer"><span><ShieldCheck v-if="selectedId === 'security'" :size="17" /><EdzioAvatar v-else class="hero-edzio-small" />{{ selectedId === 'security' ? 'Ochrona to technologia i procesy.' : selectedId === 'alert' ? 'Kod alertu i procedura szkoły.' : selectedId === 'ai' ? 'Edzio. Ten sam, którego znasz z aplikacji.' : 'Każda sprawa na swoim miejscu.' }}</span><button :aria-label="paused ? 'Wznów animację porządkowania' : 'Zatrzymaj animację porządkowania'" :aria-pressed="paused" @click="paused = !paused"><Play v-if="paused" :size="15" /><Pause v-else :size="15" /></button></div>
      </div>
    </section>
    <nav id="wybierz-funkcje" class="product-feature-switcher product-width" aria-label="Poznaj funkcje Space & Flow">
      <button v-for="section in productSections" :key="section.id" type="button" :aria-label="section.name" :aria-pressed="selectedId === section.id" @click="selectFeature(section.id)"><component :is="section.icon" :size="29" /><strong>{{ section.name }}</strong><small>{{ section.hint }}</small><ArrowUpRight class="feature-tile-arrow" :size="15" /></button>
    </nav>


    <section id="logowanie" class="product-access">
      <div class="product-width product-login-only"><div class="product-login-card"><p v-if="error" class="product-login-error" role="alert">{{ error }}</p><slot /></div></div>
    </section>

    <footer class="product-footer product-width"><a href="/" aria-label="Space & Flow — strona główna"><BrandLogo /></a><p>Przestrzeń na dokumenty. Flow do działania.</p><a href="#produkt">Wróć na górę ↑</a></footer>
  </div>
</template>

<style scoped>
.product-page{--surface:#fff;--surface-soft:#f8f7fc;--text:#242537;--secondary:#6e7081;--muted:#777a89;--border:#e9e7ef;--accent:#6a56d7;--accent-hover:#5743c4;--accent-soft:#eeebfc;--focus-ring:#aa9cf0;color:var(--text);background:#fcfbf8;font-family:Inter,system-ui,sans-serif;overflow:hidden}
.product-page *{box-sizing:border-box}.product-page a{text-decoration:none}.product-width{width:min(1180px,calc(100% - 80px));margin-inline:auto}.product-page h1,.product-page h2,.product-page h3{color:#242537;letter-spacing:-1.7px}.product-page h2{font-size:clamp(34px,3.8vw,49px);line-height:1.13;margin:15px 0 24px;font-weight:600}.product-page p{color:#6e7081;font-size:15px;line-height:1.85}.product-eyebrow{display:inline-flex;align-items:center;gap:8px;text-transform:uppercase;font-size:10px;font-weight:650;letter-spacing:1.7px;color:#777588}.product-eyebrow>span{width:6px;height:6px;border-radius:50%;background:#528c75}
.product-reveal{opacity:0;transform:translateY(20px);transition:opacity .65s ease,transform .65s ease}.product-reveal.is-visible{opacity:1;transform:translateY(0)}
.product-skip{position:fixed;top:-80px;left:20px;z-index:500;background:white;padding:12px}.product-skip:focus{top:12px}.product-header{display:flex;align-items:center;gap:32px;min-height:96px;width:min(1280px,calc(100% - 64px));margin:auto;border-bottom:1px solid #e9e7e2}.product-brand{display:flex;color:#252638}.product-header nav{display:flex;gap:30px;margin:auto}.product-header nav a{font-size:12px;color:#656471;padding:10px 0}.product-header nav a:hover{color:#6a56d7}.product-login-link{display:flex;align-items:center;gap:16px;padding:12px 19px;border:1px solid #dcd8e8;border-radius:9px;color:#302b4b;font-size:12px;font-weight:600}.product-menu-toggle{display:none}.product-brand :deep(.space-flow-word),.product-footer :deep(.space-flow-word){animation:none!important}.product-brand :deep(.space-flow-title)::before,.product-brand :deep(.space-flow-title)::after,.product-footer :deep(.space-flow-title)::before,.product-footer :deep(.space-flow-title)::after{animation:none!important;opacity:0}.product-brand :deep(.brand){color:#242537}.product-brand :deep(.space-flow-mark){color:#6a56d7}
.product-hero{display:grid;grid-template-columns:1.05fr 1fr;align-items:center;gap:65px;padding-block:90px 100px}.product-hero h1{font-size:clamp(46px,5.4vw,73px);line-height:1.08;font-weight:550;letter-spacing:-3.8px;margin:25px 0}.product-hero h1 span{color:#6a56d7}.product-hero-copy>p{max-width:450px;font-size:16px}.product-hero-actions{display:flex;align-items:flex-start;gap:21px;flex-direction:column;margin-top:30px}.product-button{display:inline-flex;align-items:center;justify-content:center;gap:22px;background:#6a56d7;color:white;padding:17px 23px;border-radius:10px;font-size:13px;font-weight:600;box-shadow:0 5px 15px #6a56d716}.product-button:hover{background:#5743c4}.product-text-link{display:inline-flex;align-items:center;gap:12px;font-size:12px;font-weight:600;color:#4d436c}.product-hero-note{display:flex;flex-wrap:wrap;gap:16px;margin-top:29px;font-size:10px;color:#7d7b86}.product-hero-note>span{display:flex;align-items:center;gap:5px}.product-hero-note svg{color:#528c75}
.product-motion{position:relative;min-width:0;background:#f1eefb;border:1px solid #e7e1f6;border-radius:23px;box-shadow:0 20px 65px #6147a90a;transform:rotate(1deg)}.motion-heading{display:flex;align-items:center;gap:7px;padding:19px 20px;color:#736a87;font-size:10px;border-bottom:1px solid #e2dcf0}.motion-dot{width:5px;height:5px;border-radius:50%;background:#79a38b}.motion-live{margin-left:auto;font-size:8px;letter-spacing:1.6px;color:#958ca5}.motion-scene{position:relative;height:350px;overflow:hidden}.motion-grid{position:absolute;inset:0;background-image:radial-gradient(#c5bddb 1px,transparent 1px);background-size:19px 19px;opacity:.4;mask-image:linear-gradient(transparent,#000,transparent)}.motion-rotor{position:absolute;top:34px;left:calc(50% - 49px);width:98px;height:98px;border-radius:50%;background:#fff;box-shadow:0 10px 40px #5d46a21b;display:grid;place-items:center;z-index:3}.motion-rotor>svg{width:76px;height:76px;color:#6a56d7}.motion-rotor :deep(.space-flow-rotor){animation:product-spin 5s linear infinite;transform-origin:24px 24px}.motion-wind{position:absolute;left:20%;top:80px;border:1px solid #c6bce3;border-left-color:transparent;border-bottom-color:transparent;width:60%;height:190px;border-radius:50%;transform:rotate(15deg);opacity:.5;animation:wind-pulse 8s ease-in-out infinite}.wind-b{width:70%;left:15%;height:220px;top:66px;transform:rotate(-15deg);animation-delay:1s}.wind-c{width:80%;left:10%;height:240px;top:55px;transform:rotate(28deg);opacity:.3;animation-delay:2s}
.motion-paper{position:absolute;z-index:2;top:136px;left:calc(50% - 119px);width:238px;display:flex;align-items:center;gap:11px;padding:12px;background:#fff;border:1px solid #e7e3ee;border-radius:10px;box-shadow:0 5px 12px #48326b0b;animation:paper-order 10s ease-in-out infinite;animation-delay:calc(var(--paper-index)*.15s);--loose-x:-70px;--loose-y:-36px;--loose-rotation:-15deg;--neat-y:0px}.paper-1{--loose-x:75px;--loose-y:-10px;--loose-rotation:14deg;--neat-y:51px}.paper-2{--loose-x:-25px;--loose-y:50px;--loose-rotation:-7deg;--neat-y:102px}.paper-symbol{width:31px;height:31px;border-radius:8px;display:grid;place-items:center;flex-shrink:0}.lavender{background:#eee8fd;color:#7a62ca}.sage{background:#e9f0e6;color:#628365}.apricot{background:#faf0e4;color:#ba8e57}.motion-paper strong{display:block;font-size:10px;font-weight:600;letter-spacing:0}.motion-paper small{display:block;margin-top:4px;font-size:8px;color:#8f8999}.paper-check{margin-left:auto;color:#67927a;animation:check-reveal 10s ease-in-out infinite}.motion-folders{position:absolute;bottom:17px;left:15px;right:15px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;z-index:4}.motion-folder{display:flex;align-items:center;justify-content:center;gap:6px;border-radius:8px;padding:9px 5px;font-size:9px;border:1px solid #fff8}.motion-folder>svg:first-child{width:16px}.motion-folder>svg:last-child{width:11px}.motion-footer{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;background:#ffffff80;border-radius:0 0 23px 23px;border-top:1px solid #e7e1f6}.motion-footer>span{display:flex;align-items:center;gap:7px;color:#777087;font-size:10px}.motion-footer button{padding:6px;border:1px solid #e6e0ef;border-radius:7px;color:#6a56d7;background:#fff}.motion-sticker{position:absolute;pointer-events:none;right:55px;bottom:-20px;display:flex;align-items:center;gap:7px;background:#edf3e8;color:#557252;padding:12px 16px;border:1px solid #dce7d5;border-radius:9px;box-shadow:0 5px 15px #1b402509;transform:rotate(-4deg);font-size:11px}.motion-paused .motion-paper,.motion-paused .paper-check,.motion-paused .motion-wind,.motion-paused :deep(.space-flow-rotor){animation-play-state:paused}
@keyframes product-spin{to{transform:rotate(360deg)}}@keyframes paper-order{0%,15%,100%{transform:translate(var(--loose-x),var(--loose-y)) rotate(var(--loose-rotation))}43%,80%{transform:translate(0,var(--neat-y)) rotate(0)}}@keyframes check-reveal{0%,25%,100%{opacity:0}45%,80%{opacity:1}}@keyframes wind-pulse{0%,100%{opacity:.15}40%,65%{opacity:.6}}
.product-ribbon{background:#f2f1ec;border-top:1px solid #eae8e1;border-bottom:1px solid #eae8e1}.product-ribbon>.product-width{display:flex;align-items:center;justify-content:space-between;gap:25px;padding-block:25px}.product-ribbon>.product-width>span{font-size:11px;color:#838078}.product-ribbon>.product-width>div{display:flex;gap:37px;flex-wrap:wrap}.product-ribbon div>span{display:flex;align-items:center;gap:8px;font-size:11px;color:#6b6876}
.product-features{padding-block:90px}.product-section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:30px;margin-bottom:25px}.product-section-heading h2{margin-bottom:20px}.product-section-heading>p{max-width:315px;margin-bottom:24px;font-size:13px}.product-feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid #e6e3dc;border-left:1px solid #e6e3dc}.product-feature{padding:30px 28px;border-right:1px solid #e6e3dc;border-bottom:1px solid #e6e3dc}.feature-symbol{display:grid;place-items:center;width:44px;height:44px;border-radius:12px;margin-bottom:25px}.feature-symbol.violet{background:#eee8fa;color:#8067b4}.feature-symbol.green{background:#e9eee4;color:#6b8266}.feature-symbol.peach{background:#f5eadf;color:#ac825e}.product-feature>small{font-size:9px;text-transform:uppercase;letter-spacing:1.2px;color:#96919d}.product-feature h3{font-size:18px;line-height:1.45;letter-spacing:-.45px;margin:10px 0 12px;font-weight:600}.product-feature p{font-size:12px;line-height:1.9;margin:0}
.product-story{display:grid;grid-template-columns:1.1fr 1fr;gap:80px;align-items:center;padding-bottom:95px}.product-story-photo{position:relative;margin:0;overflow:hidden;border-radius:18px}.product-story-photo img{display:block;width:100%;height:390px;object-fit:cover}.product-story-photo figcaption{position:absolute;bottom:18px;left:18px;right:18px;display:block;background:#fffef8ee;border:1px solid #ffffff70;border-radius:8px;padding:14px 18px;font-size:11px;color:#514e51;backdrop-filter:blur(8px)}.product-story-copy>p{font-size:13px}.product-story-copy>.product-text-link{margin-top:13px}
.product-how{background:#eeeee7;border-top:1px solid #e3e3da;border-bottom:1px solid #e3e3da;padding-block:70px}.how-brandmark{width:105px;height:105px;color:#8e89ad;margin:0 10px 25px}.product-steps{list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));padding:0;margin:15px 0 0;gap:45px}.product-steps li{border-top:1px solid #d4d5c8;padding-top:22px}.product-steps li>span{font-size:12px;font-weight:600;color:#8b8d75}.product-steps h3{font-size:18px;letter-spacing:-.4px;margin:17px 0 10px}.product-steps p{font-size:12px;max-width:290px;margin-bottom:0}
.product-devices{display:grid;grid-template-columns:1fr 1.1fr;gap:75px;align-items:center;padding-block:95px}.product-device-copy>p{font-size:13px}.device-chips{display:flex;gap:9px;margin:24px 0}.device-chips>span{display:flex;align-items:center;gap:8px;padding:9px 14px;border-radius:7px;border:1px solid #e0ddd6;color:#625c6e;font-size:11px}.product-device-tip{display:flex;gap:12px;align-items:flex-start;max-width:375px}.product-device-tip>svg{color:#8a80a9;flex-shrink:0;margin-top:3px}.product-device-tip p{font-size:11px;line-height:1.8;margin:0}.product-device-tip strong{font-weight:550;color:#595267}.product-device-photo{position:relative;margin:0}.product-device-photo>img{display:block;width:100%;height:390px;object-fit:cover;border-radius:18px}.product-notification{position:absolute;bottom:25px;left:-24px;right:30px;display:flex;align-items:center;gap:12px;padding:16px;background:#fffef9ef;backdrop-filter:blur(12px);box-shadow:0 10px 35px #241b3e12;border:1px solid #ffffffb0;border-radius:12px}.product-notification>span{width:36px;height:36px;display:grid;place-items:center;color:#7b65b4;background:#eee8fa;border-radius:10px}.product-notification strong{font-size:11px;letter-spacing:0}.product-notification p{margin:3px 0 0;font-size:11px}.product-notification>svg{margin-left:auto;color:#7a9a73}
.product-access{padding-block:75px;background:#ebe7f6;border-top:1px solid #e3ddee}.product-access-grid{display:grid;grid-template-columns:1fr 1fr;gap:90px;align-items:center}.product-access h2{font-size:clamp(36px,4vw,53px)}.product-access h2 span{color:#7662ad}.product-access-grid>div>p{max-width:370px;font-size:13px}.product-access-note{display:flex;align-items:center;gap:8px;margin-top:27px;max-width:320px;font-size:10px;color:#817591;line-height:1.7}.product-access-note svg{flex-shrink:0}.product-login-card{background:white;border:1px solid #dfd8eb;border-radius:18px;box-shadow:0 12px 32px #57447b08;padding:32px}.product-login-error{padding:12px;border:1px solid #e6c1c5;background:#fff3f4;border-radius:8px;color:#a04550!important;font-size:12px!important;margin:0 0 20px}
.product-login-card :deep(.auth){max-width:none;margin:0;padding:0;border:0;box-shadow:none;background:transparent}.product-login-card :deep(h1){font-size:25px;letter-spacing:-.8px;margin:12px 0}.product-login-card :deep(.eyebrow){font-size:9px;letter-spacing:1.4px}.product-login-card :deep(label){font-size:12px;gap:7px}.product-login-card :deep(input){background:#fcfbfe;border-color:#e5e1ee;padding:12px;color:#242537}.product-login-card :deep(.muted){font-size:12px}.product-login-card :deep(button){font-size:12px}.product-login-card :deep(form){margin-top:24px;gap:17px}.product-login-card :deep(form>small){font-size:10px}.product-footer{display:flex;align-items:center;gap:30px;padding-block:35px}.product-footer>a:first-child{color:#343047}.product-footer p{margin:auto;font-size:10px;color:#8d8797}.product-footer>a:last-child{font-size:10px;color:#847a99}.product-footer :deep(.space-flow-title){font-size:16px}.product-footer :deep(.space-flow-mark){width:30px;height:30px;color:#8b7bb8}
#funkcje,#jak-to-dziala,#na-urzadzeniach,#logowanie{scroll-margin-top:25px}
@media(min-width:1600px){.product-hero{padding-block:110px 120px}}
@media(max-width:1050px){.product-width{width:calc(100% - 56px)}.product-header{width:calc(100% - 48px);gap:20px}.product-header nav{gap:18px}.product-header nav a{font-size:11px}.product-hero{gap:35px;padding-block:65px 80px}.product-hero h1{font-size:53px;letter-spacing:-2.6px}.product-hero-copy>p{font-size:14px}.product-motion{transform:none}.motion-paper{width:206px;left:calc(50% - 103px);--loose-x:-25px}.paper-1{--loose-x:35px}.paper-2{--loose-x:-10px}.motion-folder{font-size:8px;gap:3px}.product-story,.product-devices{gap:40px}.product-feature{padding:26px 22px}.product-access-grid{gap:45px}.product-login-card{padding:27px}.product-section-heading>p{max-width:270px}}
@media(max-width:760px){.product-width{width:calc(100% - 40px)}.product-header{width:calc(100% - 32px);min-height:78px;gap:12px;flex-wrap:wrap;position:relative}.product-header nav{display:none;flex-direction:column;gap:0;order:4;width:100%;margin:0;padding:4px 0 15px}.product-header nav.is-open{display:flex}.product-header nav a{padding:12px 0;font-size:13px}.product-brand :deep(.space-flow-title){font-size:16px}.product-brand :deep(.space-flow-mark){width:32px;height:32px}.product-login-link{margin-left:auto;padding:10px 12px;font-size:11px;gap:7px}.product-menu-toggle{display:grid;padding:7px;border:0;background:transparent;color:#5d536f}.product-hero{grid-template-columns:1fr;gap:42px;padding-block:50px 65px}.product-hero h1{font-size:clamp(43px,8.5vw,64px);letter-spacing:-2.5px}.product-hero-copy>p{max-width:480px}.product-hero-actions{gap:19px}.product-motion{width:100%;max-width:500px;justify-self:center}.motion-scene{height:350px}.motion-paper{width:238px;left:calc(50% - 119px);--loose-x:-45px}.paper-1{--loose-x:45px}.paper-2{--loose-x:-15px}.product-ribbon>.product-width{flex-direction:column;align-items:flex-start;gap:17px;padding-block:22px}.product-ribbon>.product-width>div{gap:17px 22px}.product-ribbon div>span{font-size:10px}.product-features{padding-block:60px}.product-section-heading{display:block}.product-section-heading>p{max-width:450px}.product-feature-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.product-feature{padding:24px 20px}.product-feature h3{font-size:17px}.product-feature p{font-size:12px}.product-story{grid-template-columns:1fr;gap:30px;padding-bottom:60px}.product-story-photo img{height:330px}.product-story-copy{max-width:500px}.product-how{padding-block:50px}.product-how .product-section-heading{display:flex;align-items:center}.how-brandmark{width:70px;height:70px}.product-steps{gap:25px}.product-steps h3{font-size:16px}.product-devices{grid-template-columns:1fr;gap:30px;padding-block:60px}.product-device-copy{max-width:500px}.product-device-photo>img{height:330px}.product-notification{left:15px;right:15px}.product-access{padding-block:55px}.product-access-grid{grid-template-columns:1fr;gap:30px}.product-access-grid>div>p{max-width:450px}.product-login-card{padding:28px}.product-footer{gap:15px;flex-wrap:wrap}.product-footer p{order:3;width:100%;margin:0}.product-footer>a:last-child{margin-left:auto}.product-eyebrow{font-size:9px;letter-spacing:1.2px}}
@media(max-width:440px){.product-header{gap:7px}.product-brand :deep(.space-flow-title){font-size:14px}.product-brand :deep(.space-flow-mark){width:28px;height:28px}.product-brand :deep(.brand){gap:5px}.product-header .product-login-link{padding:9px 10px}.product-menu-toggle{padding:5px}.product-hero h1{font-size:44px;letter-spacing:-2.8px}.product-hero-note{gap:10px;font-size:9px}.product-button{width:100%;gap:14px;padding:16px 17px;font-size:12px}.motion-heading{padding:15px 13px;font-size:9px}.motion-live{font-size:7px;letter-spacing:1px}.motion-paper{width:216px;left:calc(50% - 108px);--loose-x:-25px}.paper-1{--loose-x:29px}.paper-2{--loose-x:-5px}.motion-folders{left:10px;right:10px;gap:5px}.motion-folder{font-size:8px;gap:3px}.motion-folder>svg:last-child{display:none}.motion-footer{padding:12px}.motion-footer>span{font-size:9px}.motion-sticker{right:45px;font-size:10px}.product-feature-grid{grid-template-columns:1fr}.product-feature{padding:25px}.feature-symbol{margin-bottom:20px}.product-feature h3{font-size:20px}.product-steps{grid-template-columns:1fr;gap:28px}.product-steps h3{font-size:19px}.product-steps p{max-width:none;font-size:13px}.product-story-photo img,.product-device-photo>img{height:270px}.product-page h2{font-size:35px;letter-spacing:-1.5px}.product-login-card{padding:23px}.product-how .how-brandmark{width:55px;height:55px}.product-notification{padding:12px;gap:8px}}
@media(prefers-reduced-motion:reduce){.product-page :deep(.space-flow-rotor),.motion-paper,.paper-check,.motion-wind{animation:none!important}.motion-paper{transform:translate(0,var(--neat-y))}.paper-check{opacity:1}.motion-wind{opacity:.2}}

/* Product feature pages share the hero and switch from the feature tiles. */
.product-page{background:#fcfaff}
.product-hero{grid-template-columns:minmax(0,1.03fr) minmax(0,1fr);gap:50px;padding-block:65px 35px;align-items:center}
.product-hero h1{font-size:clamp(43px,4.4vw,62px);letter-spacing:-2.9px;line-height:1.1;margin:22px 0}
.product-hero h1>span{display:block;color:#7138ed}
.product-hero h1:focus{outline:none}
.product-hero-copy>p{font-size:15px;max-width:495px}
.product-hero-actions{margin-top:25px;gap:17px}
.product-button{background:linear-gradient(115deg,#a44bf0,#6d31f5);border-radius:15px;box-shadow:0 8px 21px #7d33ed26}
.product-button:hover{background:linear-gradient(115deg,#9237df,#5922d8)}
.product-overview-back{padding:0;border:0;background:none;color:#a28bb6;font-size:11px;margin-bottom:18px;display:block}
.hero-feature-benefits{list-style:none;padding:0;display:grid;gap:10px;margin:22px 0 5px}
.hero-feature-benefits>li{display:flex;align-items:flex-start;gap:8px;font-size:11px;color:#8a789c;line-height:1.6}
.hero-feature-benefits svg{color:#9e7fc0;margin-top:1px;flex-shrink:0}
.feature-copy-enter{animation:feature-copy-reveal .45s ease both}
@keyframes feature-copy-reveal{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.product-motion-shelves{background:radial-gradient(ellipse at 10% 10%,#8759d2,transparent 75%),linear-gradient(145deg,#60409a,#3b245f);border-color:#6d4fa8;transform:none;border-radius:24px;box-shadow:0 20px 65px #632fb21c;min-width:0}
.product-motion-shelves .motion-heading{border-color:#ffffff14;color:#e2cff6;padding:17px 19px;font-size:10px}
.product-motion-shelves .motion-live{color:#d0b6ea;opacity:.7}
.product-motion-shelves .motion-dot{background:#b9d7c2}
.product-motion-shelves .motion-footer{background:#ffffff08;border-color:#ffffff14;border-radius:0 0 24px 24px;padding:10px 17px}
.product-motion-shelves .motion-footer>span{color:#d6c1ea;font-size:9px}
.product-motion-shelves .motion-footer button{background:#ffffff12;border-color:#ffffff20;color:#e0cdf5}
.hero-edzio-small{width:26px;height:26px;color:#d5b9f5;--surface:#73549d}
.product-motion-shelves.feature-light-demo{background:#f2edff;border-color:#e5d9f6;box-shadow:0 20px 60px #632fb209}
.feature-light-demo .motion-heading{color:#aa8dc2;border-color:#e7dcf2}
.feature-light-demo .motion-live{color:#bda9cf}
.feature-light-demo .motion-footer{background:#faf7ff;border-color:#e7dcf2}
.feature-light-demo .motion-footer>span{color:#a189b6}
.feature-light-demo .hero-edzio-small{color:#8665bd;--surface:white}
.feature-light-demo .motion-footer button{background:#fff;border-color:#e3d7ef;color:#a083bd}
.product-feature-switcher{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:10px;margin-top:10px;margin-bottom:58px;scroll-margin-top:25px}
.product-feature-switcher>button{position:relative;min-width:0;display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start;text-align:left;padding:22px 17px 20px;gap:9px;border:1px solid #eae1f6;border-radius:20px;background:#fff;box-shadow:0 4px 12px #6c3a9d05;transition:transform .2s,border-color .2s,box-shadow .2s}
.product-feature-switcher>button:hover{transform:translateY(-4px);border-color:#b59adf;box-shadow:0 8px 20px #6c3a9d12}
.product-feature-switcher>button[aria-pressed=true]{background:#f2eaff;border-color:#a779e0;box-shadow:0 4px 16px #8c52d41a}
.product-feature-switcher>button>svg:not(.feature-tile-arrow){color:#8243e9;--surface:white;width:30px;height:30px;margin-bottom:4px}
.product-feature-switcher>button>strong{font-size:12px;font-weight:650;line-height:1.35;color:#30203f;letter-spacing:-.2px}
.product-feature-switcher>button>small{font-size:10px;color:#9b85ad;line-height:1.5}
.product-feature-switcher .feature-tile-arrow{position:absolute;top:17px;right:13px;color:#b6a1cb;opacity:0;transition:opacity .2s}
.product-feature-switcher>button:hover .feature-tile-arrow,.product-feature-switcher>button[aria-pressed=true] .feature-tile-arrow{opacity:1}
.product-feature{display:block;text-align:left;border-radius:0;background:transparent;border:0;border-right:1px solid #e6e3dc;border-bottom:1px solid #e6e3dc}
.product-feature:hover{background:#f5f0fc}
.feature-symbol :deep(svg){width:26px;height:26px;--surface:white}
.feature-read-more{display:flex;align-items:center;gap:8px;margin-top:20px;color:#a283b7;font-size:10px}
.product-feature:last-child{grid-column:1/-1;display:grid;grid-template-columns:78px minmax(0,1fr);column-gap:24px;background:#f3edfc}
.product-feature:last-child>.feature-symbol{grid-column:1;grid-row:1/span 4;align-self:center;width:74px;height:74px;margin:0;background:white}
.product-feature:last-child>.feature-symbol :deep(svg){width:58px;height:58px}
.product-feature:last-child>small,.product-feature:last-child>h3,.product-feature:last-child>p,.product-feature:last-child>.feature-read-more{grid-column:2}
.product-feature:last-child>p{max-width:770px}
.product-ribbon{background:#f4effb;border-color:#ebe3f4}
@media(max-width:1100px){.product-feature-switcher{grid-template-columns:repeat(4,minmax(0,1fr))}.product-feature-switcher>button{padding:18px;min-height:138px}.product-hero{gap:28px}.product-hero h1{font-size:48px}.product-hero-copy>p{font-size:13px}.product-motion-shelves .motion-heading{padding:15px 13px}.product-feature-switcher>button>strong{font-size:13px}.product-feature-switcher>button>small{font-size:11px}}
@media(max-width:760px){.product-hero{grid-template-columns:1fr;gap:30px;padding-block:40px 25px}.product-hero h1{font-size:clamp(42px,7.5vw,58px);letter-spacing:-2.2px}.product-hero-copy>p{font-size:14px}.product-motion-shelves{max-width:550px}.product-feature-switcher{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:0;margin-bottom:40px}.product-feature-switcher>button{padding:19px;min-height:145px}.product-feature-switcher>button:last-child{grid-column:1/-1;display:grid;grid-template-columns:40px minmax(0,1fr);gap:5px 14px;min-height:95px;align-items:center}.product-feature-switcher>button:last-child>svg:not(.feature-tile-arrow){grid-column:1;grid-row:1/span 2;width:39px;height:39px;margin:0}.product-feature-switcher>button:last-child>strong,.product-feature-switcher>button:last-child>small{grid-column:2}.product-motion-shelves .motion-footer>span{font-size:9px}.product-feature:last-child{column-gap:15px}}
@media(max-width:440px){.product-hero h1{font-size:43px;letter-spacing:-2.3px}.product-hero-actions{gap:18px}.product-feature-switcher>button{min-height:138px;padding:18px}.product-feature-switcher>button>strong{font-size:13px}.product-feature-switcher>button>small{font-size:11px}.product-feature:last-child{display:block}.product-feature:last-child>.feature-symbol{width:56px;height:56px;margin-bottom:20px}.product-feature:last-child>.feature-symbol :deep(svg){width:47px;height:47px}.product-overview-back{margin-bottom:15px}}
@media(prefers-reduced-motion:reduce){.feature-copy-enter{animation:none}.product-feature-switcher>button{transition:none}.product-feature-switcher>button:hover{transform:none}}


/* Product tiles, with security first. */
.hero-security-context{max-width:480px;margin:16px 0 0}
.hero-security-context>p{font-size:11px;line-height:1.8;color:#806c8f;margin:0}
.hero-security-context>nav{display:flex;flex-wrap:wrap;gap:9px 14px;margin-top:9px}
.hero-security-context a{font-size:10px;color:#7b5897;text-decoration:underline;text-underline-offset:3px}
.security-benefit-dot{width:5px;height:5px;border-radius:50%;background:#b89acb;flex-shrink:0;margin:7px 5px 0}
.product-feature-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.product-feature:last-child{grid-column:auto;display:block}
.product-feature:last-child>.feature-symbol{width:44px;height:44px;margin-bottom:25px}
.product-feature:last-child>.feature-symbol :deep(svg){width:32px;height:32px}
@media(max-width:1250px){.product-feature-switcher{grid-template-columns:repeat(4,minmax(0,1fr))}.product-feature-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.product-feature-switcher{grid-template-columns:repeat(2,minmax(0,1fr))}.product-feature-switcher>button:last-child{grid-column:auto;display:flex;align-items:flex-start;justify-content:flex-start;gap:9px;min-height:145px}.product-feature-switcher>button:last-child>svg:not(.feature-tile-arrow){width:30px;height:30px;margin-bottom:4px}.hero-security-context{margin-top:15px}}
@media(max-width:440px){.product-feature-grid{grid-template-columns:1fr}.product-feature-switcher>button:last-child{min-height:138px}.product-feature:last-child>.feature-symbol{width:44px;height:44px}.product-feature:last-child>.feature-symbol :deep(svg){width:32px;height:32px}}




.product-login-only{max-width:520px}
</style>
