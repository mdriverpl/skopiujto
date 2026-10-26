import test from 'node:test'
import assert from 'node:assert/strict'
import { mailSenderKind } from './mailSenderKind.js'

test('a government-looking address never hides a detected phishing warning', () => {
  assert.equal(mailSenderKind({ government: { suffix: 'gov.in' }, phishing_warning: 'Podejrzenie phishingu: żądanie danych' }), 'phishing')
  assert.equal(mailSenderKind({ government: { suffix: 'gov.pl' }, spam_protected: true }), 'government')
})

test('company status requires an actual assignment and unrelated letters cannot imply trust', () => {
  assert.equal(mailSenderKind({ sender_name: 'Firma Klient' }), 'other')
  assert.equal(mailSenderKind({ company: { id: 'company' }, safe: true }), 'company')
  assert.equal(mailSenderKind({ folder: 'spam', category: 'spam' }), 'spam')
})

test('bank impersonation takes precedence over a company assignment and category', () => {
  const message = { sender_name: 'iPKO biznes', sender_email: 'webmaster@72c9eed974.nxcli.io',
    folder: 'inbox', company: { id: 'bank' }, safe: true,
    phishing_warning: 'Podejrzenie phishingu: domena nadawcy nie odpowiada domenom banku.' }
  assert.equal(mailSenderKind(message), 'phishing')
  assert.equal(mailSenderKind({ ...message, folder: 'sent' }), 'sent')
  assert.equal(mailSenderKind({ ...message, folder: 'drafts' }), 'draft')
})
