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
