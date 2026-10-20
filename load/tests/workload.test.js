import assert from 'node:assert/strict';
import test from 'node:test';
import {assignment, hash, operationFor, pageFor, PROFILES, random, validateManifest} from '../workload.js';

function manifest() {
    return {
        schema_version: 1,
        company_count: 100,
        active_company_count: 25,
        page_size: 20,
        sort: ['criadoEm,desc', 'id,desc'],
        companies: Array.from({length: 100}, (_, company) => ({
            tenant_id: String(1001 + company * 2),
            total_clients: 5000,
            total_orders: 20000,
            total_items: 60000,
            write_orders: Array.from({length: 20}, (_, slot) => ({
                id: String(50001 + company * 100 + slot),
                initial_status: 'ABERTO',
            })),
        })),
    };
}

test('500 VUs usam 25 empresas fixas e 500 pedidos sem colisão', () => {
    const data = manifest();
    validateManifest(data);
    const tenants = new Map();
    const orders = new Set();
    for (let user = 1; user <= 500; user += 1) {
        const selected = assignment(data, user);
        tenants.set(selected.company.tenant_id, (tenants.get(selected.company.tenant_id) || 0) + 1);
        assert.equal(orders.has(selected.orderId), false);
        orders.add(selected.orderId);
    }
    assert.equal(tenants.size, 25);
    assert.equal(orders.size, 500);
    assert.deepEqual([...tenants.values()], Array(25).fill(20));
});

test('o conjunto ativo permanece igual nas cinco concorrências', () => {
    const data = manifest();
    const expected = new Set(data.companies.slice(0, 25).map(company => company.tenant_id));
    for (const users of [25, 50, 100, 250, 500]) {
        const active = new Set(Array.from({length: users}, (_, index) => assignment(data, index + 1).company.tenant_id));
        assert.deepEqual(active, expected);
    }
});

test('sementes pareadas reproduzem decisões e páginas por VU', () => {
    const left = random(hash('paired-seed|measurement|7'));
    const right = random(hash('paired-seed|measurement|7'));
    assert.deepEqual(Array.from({length: 1000}, () => left()), Array.from({length: 1000}, () => right()));
    assert.notEqual(hash('paired-seed|measurement|7'), hash('paired-seed|warmup|7'));
});

test('cada bloco completo contém exatamente a proporção de escritas planejada', () => {
    for (const [profile, expectedWrites] of Object.entries(PROFILES)) {
        const generator = random(hash(profile));
        const operations = operationFor(generator, expectedWrites, 0);
        assert.equal(operations.filter(Boolean).length, expectedWrites);
        assert.equal(operationFor(generator, expectedWrites, 1), null);
    }
});

test('80% das leituras atingem as primeiras 200 páginas e nunca saem das 1000 páginas', () => {
    const generator = random(721);
    let hotReads = 0;
    for (let index = 0; index < 100000; index += 1) {
        const page = pageFor(generator, 1000);
        assert.ok(page >= 0 && page < 1000);
        if (page < 200) {
            hotReads += 1;
        }
    }
    assert.ok(hotReads > 79000 && hotReads < 81000);
});

test('manifesto rejeita pedidos repetidos, fora de ABERTO ou volumes incorretos', () => {
    const duplicate = manifest();
    duplicate.companies[1].write_orders[0].id = duplicate.companies[0].write_orders[0].id;
    assert.throws(() => validateManifest(duplicate));
    const changed = manifest();
    changed.companies[1].write_orders[0].initial_status = 'CONFIRMADO';
    assert.throws(() => validateManifest(changed));
    const size = manifest();
    size.companies[0].total_orders = 100;
    assert.throws(() => validateManifest(size));
});
