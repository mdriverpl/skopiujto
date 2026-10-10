export const themes = [
  { id: 'normal', label: 'Normalny', color: '#6654d9' },
  { id: 'sweet', label: 'Słodki', color: '#b83274' },
  { id: 'dark', label: 'Ciemny', color: '#a99aff' },
  { id: 'colorful', label: 'Kolorowy', color: '#096d94' },
]
export function savedTheme() {
  try {
    const stored = localStorage.getItem('edokumenty-theme')
    return themes.some(theme => theme.id === stored) ? stored : 'normal'
  } catch { return 'normal' }
}
export function applyTheme(id) {
  const theme = themes.find(theme => theme.id === id) || themes[0]
  document.documentElement.dataset.theme = theme.id
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme.color)
  try { localStorage.setItem('edokumenty-theme', theme.id) } catch {}
  return theme.id
}
