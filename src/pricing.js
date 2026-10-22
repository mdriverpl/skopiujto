import catalog from '../backend/pricing_catalog.json' with { type: 'json' }
export const { serverPlans, databasePlans, databaseEngines, infrastructureOptions } = catalog
export const formatMoney = value => new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 }).format(value) + ' z\u0142'

export function infrastructureForPlan(planId) {
  const plan = serverPlans.find(plan => plan.id === planId) || serverPlans[0]
  return infrastructureOptions.map(option => option.id === 'ha'
    ? { ...option, price: plan.monthly, description: `Drugi serwer ${plan.id} — łącznie 2 × ${plan.id}` }
    : option)
}

export function boundedQuantity(value, min, max, step = 1) {
  const number = Number(value)
  return Math.max(min, Math.min(max, Math.ceil((Number.isFinite(number) ? number : min) / step) * step))
}

export function calculatePricing(users, storage, selected, planId = 'S1', databaseConfig = {}) {
  const userCount = boundedQuantity(users, 1, 500)
  const storageGb = boundedQuantity(storage, 100, 10000, 100)
  const plan = serverPlans.find(plan => plan.id === planId) || serverPlans[0]
  const options = infrastructureForPlan(plan.id).filter(option => selected.includes(option.id))
  const serverCount = options.some(option => option.id === 'ha') ? 2 : 1
  const server = { plan, count: serverCount, total: Math.round(plan.monthly * serverCount * 100) / 100 }
  const databasePlan = databasePlans.find(plan => plan.id === databaseConfig.planId) || databasePlans[0]
  const engine = databaseEngines.includes(databaseConfig.engine) ? databaseConfig.engine : databaseEngines[0]
  const databaseEnabled = databaseConfig.planId !== 'none'
  const database = { enabled: databaseEnabled, plan: databaseEnabled ? databasePlan : null, engine,
    ha: databaseEnabled && databaseConfig.ha === true,
    total: databaseEnabled ? (databaseConfig.ha === true ? databasePlan.ha : databasePlan.single) : 0 }
  const base = catalog.workspaceBase
  const userCost = userCount * catalog.userRate
  const workspace = base + userCost
  const disk = storageGb / 100 * catalog.storageRate
  return { users: userCount, storage: storageGb, base, userCost, workspace, disk, options, server, database,
    total: Math.round((workspace + disk + plan.monthly + database.total + options.reduce((sum, option) => sum + option.price, 0)) * 100) / 100 }
}

export function configurationText(pricing) {
  return [
    'SpaceFlow — wycena demonstracyjna', 'Twoja prywatna przestrzeń pracy', '',
    `SpaceFlow Workspace: ${pricing.users} użytkowników — ${formatMoney(pricing.workspace)}/mies. netto`,
    'Abonament netto: 500 zł + 5 zł/użytk./mies.',
    `Cena podstawowa: ${formatMoney(pricing.base)}/mies. netto`,
    `Użytkownicy: ${pricing.users} × 5 zł = ${formatMoney(pricing.userCost)}/mies. netto`,
    `Serwer ${pricing.server.plan.id}: ${pricing.server.plan.vcpu} vCPU, ${pricing.server.plan.ram} GB RAM, ${pricing.server.plan.nvme} GB NVMe`,
    `Serwery: ${pricing.server.count} × ${formatMoney(pricing.server.plan.monthly)} = ${formatMoney(pricing.server.total)}/mies. netto`,
    ...(pricing.server.count === 2 ? ['HA: włączone — koszt drugiego serwera uwzględniony powyżej'] : []),
    ...(pricing.database.enabled ? [
      `Baza danych ${pricing.database.engine} ${pricing.database.plan.id}: ${pricing.database.plan.vcpu} vCPU, ${pricing.database.plan.ram} GB RAM, ${pricing.database.plan.disk} GB dysku`,
      `Wariant bazy: ${pricing.database.ha ? 'z repliką (HA)' : 'pojedyncza'} — ${formatMoney(pricing.database.total)}/mies. netto`,
    ] : ['Serwer bazy danych: Brak — 0 zł/mies. netto']),
    ...pricing.options.filter(option => option.id !== 'ha').map(option => `${option.name}: ${formatMoney(option.price)}/mies. netto`),
    `Przestrzeń dyskowa: ${pricing.storage} GB — ${formatMoney(pricing.disk)}/mies. netto`, '',
    `Miesięcznie netto: ${formatMoney(pricing.total)}`,
    'Ceny demonstracyjne • + VAT • wdrożenie wyceniane osobno',
  ].join('\n')
}
