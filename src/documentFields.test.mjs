import test from 'node:test'
import assert from 'node:assert/strict'
import { documentFields, documentText, fillDocument, plainDocument } from './documentFields.js'

test('repeated fields use one input while different parties have distinct inputs', () => {
  const source = plainDocument('Sprzedający: [imię sprzedającego]. Kupujący: [imię kupującego].\nPodpis: [ Imię sprzedającego ]. Cena: [cena]')
  assert.deepEqual(documentFields(source).map(field => field.key), ['imię sprzedającego', 'imię kupującego', 'cena'])
  const filled = fillDocument(source, { 'imię sprzedającego': 'Anna', 'imię kupującego': 'Jan', cena: '1200 zł' })
  assert.equal(documentText(filled), 'Sprzedający: Anna. Kupujący: Jan.\nPodpis: Anna. Cena: 1200 zł')
  assert.equal(documentText(source).includes('[cena]'), true)
})

test('changing or clearing data recalculates from the original document', () => {
  const source = plainDocument('Cena: [cena]. Data: [data]')
  assert.equal(documentText(fillDocument(source, { cena: '100 zł' })), 'Cena: 100 zł. Data: [data]')
  assert.equal(documentText(fillDocument(source, { cena: '200 zł' })), 'Cena: 200 zł. Data: [data]')
  assert.equal(documentText(fillDocument(source, { cena: '' })), 'Cena: [cena]. Data: [data]')
})

test('placeholders split across formatting retain surrounding text and marks', () => {
  const source = { type: 'doc', content: [{ type: 'paragraph', content: [
    { type: 'text', text: 'Cena: ' },
    { type: 'text', text: '[ce', marks: [{ type: 'bold' }] },
    { type: 'text', text: 'na] netto.' },
    { type: 'hardBreak' }, { type: 'text', text: 'Data: [data]' }
  ] }] }
  assert.deepEqual(documentFields(source).map(field => field.key), ['cena', 'data'])
  const filled = fillDocument(source, { cena: '300 zł', data: '10.10.2026' })
  assert.equal(documentText(filled), 'Cena: 300 zł netto.\nData: 10.10.2026')
  assert.deepEqual(filled.content[0].content.find(node => node.text === '300 zł').marks, [{ type: 'bold' }])
})

test('user values stay literal, including HTML and brackets', () => {
  const filled = fillDocument(plainDocument('[nazwa] / [cena]'), { nazwa: '<script>[cena]</script>', cena: '100' })
  assert.equal(documentText(filled), '<script>[cena]</script> / 100')
  assert.equal(filled.content[0].content.every(node => node.type === 'text'), true)
})
