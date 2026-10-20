export const PROFILES = {
    '100-0': 0,
    '90-10': 10,
    '70-30': 30,
    '50-50': 50,
};

export function hash(value) {
    let state = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
        state = Math.imul(state ^ value.charCodeAt(index), 16777619);
    }
    return state >>> 0;
}

export function random(seed) {
    let state = seed >>> 0;
    return function next() {
        state += 0x6D2B79F5;
        let value = state;
        value = Math.imul(value ^ (value >>> 15), value | 1);
        value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
        return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
}

export function assignment(manifest, virtualUser) {
    if (!Number.isInteger(virtualUser) || virtualUser < 1 || virtualUser > 500) {
        throw new Error('VU precisa estar entre 1 e 500.');
    }
    const companyIndex = (virtualUser - 1) % manifest.active_company_count;
    const slot = Math.floor((virtualUser - 1) / manifest.active_company_count);
    const company = manifest.companies[companyIndex];
    return {
        company,
        orderId: company.write_orders[slot].id,
        slot,
    };
}

export function pageFor(next, totalPages) {
    const hotPages = Math.max(1, Math.floor(totalPages * 0.2));
    if (next() < 0.8 || hotPages === totalPages) {
        return Math.floor(next() * hotPages);
    }
    return hotPages + Math.floor(next() * (totalPages - hotPages));
}

export function operationFor(next, writePercent, iteration) {
    const position = iteration % 100;
    if (position === 0) {
        const operations = Array.from({length: 100}, (_, index) => index < writePercent);
        for (let index = operations.length - 1; index > 0; index -= 1) {
            const target = Math.floor(next() * (index + 1));
            const previous = operations[index];
            operations[index] = operations[target];
            operations[target] = previous;
        }
        return operations;
    }
    return null;
}

export function validateManifest(manifest) {
    if (manifest.schema_version !== 1 || manifest.company_count !== 100
            || manifest.active_company_count !== 25 || manifest.page_size !== 20
            || JSON.stringify(manifest.sort) !== JSON.stringify(['criadoEm,desc', 'id,desc'])
            || !Array.isArray(manifest.companies) || manifest.companies.length !== 100) {
        throw new Error('Manifesto incompatível com o desenho experimental.');
    }
    const tenants = new Set();
    const orders = new Set();
    for (const company of manifest.companies) {
        if (!/^[1-9][0-9]{0,18}$/.test(company.tenant_id) || tenants.has(company.tenant_id)
                || company.total_orders !== 20000 || company.total_clients !== 5000
                || company.total_items !== 60000 || company.write_orders.length !== 20) {
            throw new Error('Empresa inválida no manifesto.');
        }
        tenants.add(company.tenant_id);
        for (const order of company.write_orders) {
            if (!/^[1-9][0-9]{0,18}$/.test(order.id) || orders.has(order.id)
                    || order.initial_status !== 'ABERTO') {
                throw new Error('Pedido reservado inválido no manifesto.');
            }
            orders.add(order.id);
        }
    }
}
