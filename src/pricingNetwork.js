export function buildPricingNetwork(pricing, selected) {
  const server = pricing.server.plan
  const database = pricing.database
  return {
    users: pricing.users,
    waf: selected.includes('waf'),
    vpn: selected.includes('vpn'),
    servers: Array.from({ length: pricing.server.count }, (_, index) => ({
      id: `server-${index + 1}`, name: `Serwer ${index + 1}`, plan: server.id,
      specs: `${server.vcpu} vCPU · ${server.ram} GB RAM`, disk: `${server.nvme} GB NVMe`,
    })),
    databases: database.enabled ? Array.from({ length: database.ha ? 2 : 1 }, (_, index) => ({
      id: `database-${index + 1}`, name: index === 0 ? 'Baza główna' : 'Replika bazy',
      engine: database.engine, plan: database.plan.id,
      specs: `${database.plan.vcpu} vCPU · ${database.plan.ram} GB RAM`, disk: `${database.plan.disk} GB dysku`,
    })) : [],
    storage: pricing.storage,
    backup: selected.includes('backup'),
    logs: selected.includes('logs'),
    logServer: selected.includes('logs') ? { id: 'logs-server', name: `Serwer ${pricing.server.count + 1}` } : null,
    serverCount: pricing.server.count + (selected.includes('logs') ? 1 : 0),
  }
}
