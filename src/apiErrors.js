export function apiErrorDetail(detail) {
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  const labels = { name: 'Nazwa', email: 'Adres e-mail', password: 'Hasło', current_password: 'Obecne hasło', new_password: 'Nowe hasło', fields: 'Pola', version: 'Wersja', field_sources: 'Powiązania pól', values: 'Dane', title: 'Tytuł', assignee_id: 'Odbiorca' }
  return detail.map(issue => {
    const location = (issue.loc || []).filter(part => part !== 'body')
    const label = labels[location[0]] || 'Dane'
    if (issue.type === 'missing') {
      if (location[0] === 'password') return 'Hasło: serwer wymaga hasła. Przy dodawaniu użytkownika hasło powinno być generowane automatycznie — uruchom ponownie backend i odśwież stronę.'
      if (['name', 'email', 'current_password', 'new_password'].includes(location[0])) return `${label}: uzupełnij wymagane pole.`
      return `${label}: brak wymaganej wartości. Odśwież dane i spróbuj ponownie.`
    }
    if (issue.type === 'value_error') return `${label}: ${(issue.msg || 'Nieprawidłowa wartość.').replace(/^Value error, /, '')}`
    if (issue.type === 'string_too_long') return `${label}: wpisana wartość jest za długa.`
    if (issue.type === 'string_too_short') return `${label}: uzupełnij wartość.`
    return `${label}: nieprawidłowa wartość.`
  }).join(' ') || null
}
