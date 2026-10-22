import test from 'node:test'
import assert from 'node:assert/strict'
import { calculatePricing } from './pricing.js'
import { buildPricingNetwork } from './pricingNetwork.js'

test('VPN appears in the topology only when selected', () => {
  const price = calculatePricing(20, 100, ['vpn'])
  assert.equal(buildPricingNetwork(price, ['vpn']).vpn, true)
  assert.equal(buildPricingNetwork(price, []).vpn, false)
})

test('network shows one application server and no managed database when none is selected', () => {
  const network = buildPricingNetwork(calculatePricing(20, 100, [], 'S2', { planId: 'none', ha: true }), [])
  assert.equal(network.servers.length, 1)
  assert.equal(network.servers[0].plan, 'S2')
  assert.equal(network.databases.length, 0)
  assert.equal(network.users, 20)
  assert.equal(network.waf, false)
  assert.equal(network.backup, false)
  assert.equal(network.logs, false)
})

test('HA draws two servers and a database replica with selected capacities and services', () => {
  const selected = ['ha', 'waf', 'backup', 'logs']
  const network = buildPricingNetwork(calculatePricing(45, 2000, selected, 'S8',
    { planId: 'S4', engine: 'MariaDB', ha: true }), selected)
  assert.equal(network.servers.length, 2)
  assert.equal(network.databases.length, 2)
  assert.equal(network.servers[1].plan, 'S8')
  assert.equal(network.servers[1].specs, '4 vCPU · 8 GB RAM')
  assert.equal(network.databases[1].name, 'Replika bazy')
  assert.equal(network.databases[1].engine, 'MariaDB')
  assert.equal(network.storage, 2000)
  assert.equal(network.waf, true)
  assert.equal(network.backup, true)
  assert.equal(network.logs, true)
})

test('server HA and database HA produce independent node counts', () => {
  for (const serverHa of [false, true]) {
    for (const databaseHa of [false, true]) {
      const selected = serverHa ? ['ha'] : []
      const network = buildPricingNetwork(calculatePricing(20, 100, selected, 'S1',
        { planId: 'S2', ha: databaseHa }), selected)
      assert.equal(network.servers.length, serverHa ? 2 : 1)
      assert.equal(network.databases.length, databaseHa ? 2 : 1)
    }
  }
})

test('log analysis adds a separate third server with HA and second server without HA', () => {
  for (const ha of [false, true]) {
    const selected = ha ? ['ha', 'logs'] : ['logs']
    const price = calculatePricing(20, 100, selected)
    const network = buildPricingNetwork(price, selected)
    assert.equal(network.servers.length, ha ? 2 : 1)
    assert.equal(network.serverCount, ha ? 3 : 2)
    assert.equal(network.logServer.name, ha ? 'Serwer 3' : 'Serwer 2')
    assert.equal(price.options.find(option => option.id === 'logs').price, 99)
    const withoutLogs = buildPricingNetwork(price, selected.filter(option => option !== 'logs'))
    assert.equal(withoutLogs.logServer, null)
    assert.equal(withoutLogs.serverCount, ha ? 2 : 1)
  }
})
