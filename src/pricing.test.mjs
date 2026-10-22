import test from 'node:test'
import assert from 'node:assert/strict'
import { boundedQuantity, calculatePricing, configurationText, databaseEngines, databasePlans, serverPlans } from './pricing.js'

test('optional VPN adds exactly 19 PLN and appears in the configuration export', () => {
  const basic = calculatePricing(20, 100, [])
  const vpn = calculatePricing(20, 100, ['vpn', 'vpn'])
  assert.equal(Math.round((vpn.total - basic.total) * 100), 1900)
  assert.equal(vpn.options.filter(option => option.id === 'vpn').length, 1)
  assert.match(configurationText(vpn), /VPN: 19 zł/)
})

test('example includes the default S1 server alongside application, disk and options', () => {
  const price = calculatePricing(19, 100, ['waf', 'backup'])
  assert.equal(price.workspace, 595)
  assert.equal(price.disk, 20)
  assert.equal(price.server.plan.id, 'S1')
  assert.equal(price.server.total, 19)
  assert.equal(price.database.engine, 'PostgreSQL')
  assert.equal(price.database.total, 41.8)
  assert.equal(price.total, 793.8)
})

test('all infrastructure options add their monthly fees once', () => {
  const price = calculatePricing(19, 100, ['waf', 'logs', 'ha', 'replica', 'backup', 'waf', 'unknown'])
  assert.equal(price.total, 911.8)
  assert.equal(price.options.length, 4)
})

test('user and disk changes recalculate the total without optional services', () => {
  const price = calculatePricing('30', '500', [])
  assert.equal(price.workspace, 650)
  assert.equal(price.disk, 100)
  assert.equal(price.total, 810.8)
})

test('empty and invalid quantities stay finite and within supported limits', () => {
  assert.equal(boundedQuantity('', 1, 500), 1)
  assert.equal(boundedQuantity(NaN, 1, 500), 1)
  assert.equal(boundedQuantity(Infinity, 100, 10000, 100), 100)
  assert.equal(boundedQuantity(-50, 100, 10000, 100), 100)
  assert.equal(boundedQuantity(100001, 100, 10000, 100), 10000)
  assert.equal(boundedQuantity(150, 100, 10000, 100), 200)
  assert.equal(boundedQuantity(1.5, 1, 500), 2)
  assert.equal(calculatePricing('', '', []).total, 585.8)
})

test('copied and downloaded quote includes selected services and pricing caveat without company data', () => {
  const text = configurationText(calculatePricing(19, 100, ['waf', 'backup']))
  assert.doesNotMatch(text, /Nazwa firmy|Domena firmy|Nie podano/)
  assert.match(text, /WAF: 69 zł/)
  assert.match(text, /Backup S3: 49 zł/)
  assert.doesNotMatch(text, /Analiza logów|Replika bazy/)
  assert.match(text, /Abonament netto: 500 zł \+ 5 zł\/użytk.\/mies./)
  assert.match(text, /Miesięcznie netto: 793,8 zł/)
  assert.match(text, /Ceny demonstracyjne • \+ VAT • wdrożenie wyceniane osobno/)
})

test('every server plan uses its monthly price and HA adds exactly one identical server', () => {
  for (const plan of serverPlans) {
    const single = calculatePricing(20, 100, [], plan.id)
    const ha = calculatePricing(20, 100, ['ha', 'ha'], plan.id)
    assert.equal(single.server.plan.id, plan.id)
    assert.equal(single.server.count, 1)
    assert.equal(single.server.total, plan.monthly)
    assert.equal(single.total, Math.round((661.8 + plan.monthly) * 100) / 100)
    assert.equal(ha.server.count, 2)
    assert.equal(ha.server.total, Math.round(plan.monthly * 200) / 100)
    assert.equal(ha.total, Math.round((661.8 + plan.monthly * 2) * 100) / 100)
    assert.equal(ha.options.length, 1)
    assert.equal(ha.options[0].price, plan.monthly)
  }
})

test('changing plan with HA enabled updates both servers without fractional penny errors', () => {
  assert.equal(calculatePricing(20, 100, ['ha'], 'S2').total, 722.7)
  assert.equal(calculatePricing(20, 100, ['ha'], 'S32').total, 1331.7)
  assert.equal(calculatePricing(20, 100, [], 'unknown').server.plan.id, 'S1')
})

test('export itemizes HA as two servers and uses Polish decimal prices', () => {
  const text = configurationText(calculatePricing(20, 100, ['ha'], 'S2'))
  assert.match(text, /Serwer S2: 1 vCPU, 2 GB RAM, 30 GB NVMe/)
  assert.match(text, /Serwery: 2 × 30,45 zł = 60,9 zł\/mies. netto/)
  assert.match(text, /HA: włączone/)
  assert.match(text, /Miesięcznie netto: 722,7 zł/)
  assert.doesNotMatch(text, /199 zł/)
})

test('all database plans and engines use the supplied standalone and replica prices', () => {
  for (const plan of databasePlans) {
    for (const engine of databaseEngines) {
      for (const ha of [false, true]) {
        const price = calculatePricing(20, 100, [], 'S1', { planId: plan.id, engine, ha })
        assert.equal(price.database.engine, engine)
        assert.equal(price.database.plan.id, plan.id)
        assert.equal(price.database.ha, ha)
        assert.equal(price.database.total, ha ? plan.ha : plan.single)
        assert.equal(price.total, Math.round((639 + (ha ? plan.ha : plan.single)) * 100) / 100)
        assert.equal(price.server.count, 1)
      }
    }
  }
})

test('database HA and server HA are independent and replica is never charged again', () => {
  const config = { planId: 'S2', engine: 'MySQL', ha: true }
  const databaseHa = calculatePricing(20, 100, ['replica'], 'S2', config)
  const bothHa = calculatePricing(20, 100, ['ha', 'replica'], 'S2', config)
  assert.equal(databaseHa.server.count, 1)
  assert.equal(databaseHa.database.total, 133.98)
  assert.equal(databaseHa.total, 784.43)
  assert.equal(bothHa.server.count, 2)
  assert.equal(bothHa.total, 814.88)
  assert.ok(bothHa.options.every(option => option.id !== 'replica'))
  const text = configurationText(bothHa)
  assert.match(text, /Baza danych MySQL S2: 1 vCPU, 2 GB RAM, 30 GB dysku/)
  assert.match(text, /Wariant bazy: z repliką \(HA\) — 133,98 zł/)
  assert.match(text, /Miesięcznie netto: 814,88 zł/)
})

test('invalid database selections fall back to a single PostgreSQL S1 database', () => {
  const price = calculatePricing(20, 100, [], 'S1', { planId: 'unknown', engine: 'unknown', ha: 'false' })
  assert.equal(price.database.plan.id, 'S1')
  assert.equal(price.database.engine, 'PostgreSQL')
  assert.equal(price.database.ha, false)
  assert.equal(price.database.total, 41.8)
})

test('no database costs zero even with database HA selected and exports safely', () => {
  for (const ha of [false, true]) {
    const price = calculatePricing(20, 100, ['ha'], 'S2', { planId: 'none', engine: 'PostgreSQL', ha })
    assert.equal(price.database.enabled, false)
    assert.equal(price.database.plan, null)
    assert.equal(price.database.ha, false)
    assert.equal(price.database.total, 0)
    assert.equal(price.total, 680.9)
    const text = configurationText(price)
    assert.match(text, /Serwer bazy danych: Brak — 0 zł/)
    assert.doesNotMatch(text, /Wariant bazy:/)
  }
})
