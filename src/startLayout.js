export function readStartLayout(userId) {
  try { return localStorage.getItem(`edokumenty-start-layout:${userId || 'guest'}`) === 'v1' ? 'v1' : 'v2' } catch { return 'v2' }
}
export function saveStartLayout(userId, layout) {
  if (!['v1', 'v2'].includes(layout)) return
  try { localStorage.setItem(`edokumenty-start-layout:${userId || 'guest'}`, layout) } catch {}
}
