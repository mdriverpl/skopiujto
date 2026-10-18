export function normalizeUnifiedMail(items, emails) {
  const native = new Map(emails.map(message => [message.id, message]))
  return items.flatMap(item => {
    if (item.direction === 'outgoing') return []
    if (item.source === 'email') {
      const email = native.get(item.source_id)
      return email && isReceivedMessage(email) ? [{ ...email, center: item }] : []
    }
    return [{ id: item.id, center: item, folder: 'inbox', sender_name: item.sender || '', sender_email: '',
      recipient: item.recipient || '', subject: item.title || '', content: item.content || '',
      created_at: item.source === 'edelivery' ? `${item.created_at}T12:00:00` : item.created_at,
      unread: !!item.unread, starred: false, category: '', label: '', attachments: [] }]
  })
}

export async function loadUnifiedMail(api) {
  const [emails, first] = await Promise.all([api('/client-mail'), api('/message-center?direction=incoming&limit=100&offset=0')])
  const items = [...first.items]
  for (let offset = 100; offset < first.total; offset += 100) {
    const page = await api(`/message-center?direction=incoming&limit=100&offset=${offset}`)
    items.push(...page.items)
  }
  return normalizeUnifiedMail(items, emails)
}

export const isEmailMessage = message => !!message && (!message.center || message.center.source === 'email')
export const isSpamMessage = message => message.folder === 'spam' || message.category === 'spam'
export const isReceivedMessage = message => !isSpamMessage(message) && message.folder === 'inbox' && message.center?.direction !== 'outgoing'
export function sourceKind(message) {
  return !message?.center ? 'email' : message.center.channel === 'user' ? 'portal' :
    ['email', 'sms', 'edelivery'].includes(message.center.channel) ? message.center.channel : 'other'
}
