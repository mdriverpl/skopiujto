import { ref } from 'vue'

export const installAvailable = ref(false)
export const installed = ref(false)
let promptEvent = null

export function initializePwa() {
  installed.value = window.matchMedia('(display-mode: standalone)').matches
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault()
    promptEvent = event
    installAvailable.value = true
  })
  window.addEventListener('appinstalled', () => {
    installed.value = true
    installAvailable.value = false
    promptEvent = null
  })
}
export async function installPwa() {
  if (!promptEvent) return false
  const event = promptEvent
  promptEvent = null
  installAvailable.value = false
  await event.prompt()
  return (await event.userChoice).outcome === 'accepted'
}
export function applicationServerKey(value) {
  const data = atob(value.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(data, character => character.charCodeAt(0))
}
export async function registerPwa() {
  if (!window.isSecureContext || !('serviceWorker' in navigator)) {
    throw new Error('Instalacja i powiadomienia wymagają HTTPS oraz obsługiwanej przeglądarki.')
  }
  await navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
  return navigator.serviceWorker.ready
}
