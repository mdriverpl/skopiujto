import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './themes.css'
import { savedTheme, applyTheme } from './theme.js'
import { initializePwa, registerPwa } from './pwa.js'
applyTheme(savedTheme())
initializePwa()
createApp(App).mount('#app')
if (import.meta.env.PROD) registerPwa().catch(error => console.warn('PWA:', error.message))
