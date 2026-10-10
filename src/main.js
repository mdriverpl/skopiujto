import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './themes.css'
import { savedTheme, applyTheme } from './theme.js'
applyTheme(savedTheme())
createApp(App).mount('#app')
if ('serviceWorker' in navigator && import.meta.env.PROD) navigator.serviceWorker.register('/sw.js')
