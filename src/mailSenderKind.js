export function mailSenderKind(message) {
  if (message.folder === 'drafts') return 'draft'
  if (message.folder === 'sent') return 'sent'
  if (message.phishing_warning || (!message.safe && message.category_reason?.startsWith('Podejrzenie phishingu:'))) return 'phishing'
  if (message.government) return 'government'
  if (message.company) return 'company'
  if (message.blocked || message.folder === 'spam' || message.category === 'spam') return 'spam'
  if (['newsletter', 'advertisement'].includes(message.category)) return 'marketing'
  if (message.category === 'notification') return 'notification'
  return 'other'
}
