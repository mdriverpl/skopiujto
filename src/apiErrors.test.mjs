import test from 'node:test'
import assert from 'node:assert/strict'
import { apiErrorDetail } from './apiErrors.js'
test('validation errors identify missing versions and custom field rules without echoing submitted data', () => {
  assert.match(apiErrorDetail([{ loc: ['body', 'version'], type: 'missing', input: { secret: 'private' } }]), /Wersja: brak/)
  const message = apiErrorDetail([{ loc: ['body', 'fields'], type: 'value_error', msg: 'Value error, Nazwy pól nie mogą się powtarzać.' }])
  assert.equal(message, 'Pola: Nazwy pól nie mogą się powtarzać.')
  assert.equal(apiErrorDetail('Słownik został zmieniony.'), 'Słownik został zmieniony.')
  assert.equal(apiErrorDetail(null), null)
})

test('account errors identify email and explain an outdated server requiring a password', () => {
  assert.equal(apiErrorDetail([{ loc: ['body', 'email'], type: 'missing' }]), 'Adres e-mail: uzupełnij wymagane pole.')
  const error = apiErrorDetail([{ loc: ['body', 'password'], type: 'missing', input: { password: 'secret' } }])
  assert.match(error, /uruchom ponownie backend/)
  assert.ok(!error.includes('secret'))
  assert.match(apiErrorDetail([{ loc: ['body', 'current_password'], type: 'string_too_short' }]), /^Obecne hasło:/)
})
