import { createApp, defineAsyncComponent } from 'vue'
import App from './App.vue'
import './style.css'
import './themes.css'
import { savedTheme, applyTheme } from './theme.js'
import { initializePwa, registerPwa } from './pwa.js'
applyTheme(savedTheme())
initializePwa()
const isPricingPage = window.location.pathname.replace(/\/+$/, '') === '/wycena'
const rootComponent = isPricingPage ? defineAsyncComponent(() => import('./PricingPage.vue')) : App
createApp(rootComponent).mount('#app')
if (import.meta.env.PROD) registerPwa().catch(error => console.warn('PWA:', error.message))
