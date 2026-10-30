import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {assignment, hash, operationFor, pageFor, PROFILES, random, validateManifest} from '../workload.js';

const source = readFileSync(new URL('../experiment.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '')
    .replace('export default function (data)', 'function iterationForTest(data)')
    .replace(/export /g, '')
    + '\nglobalThis.hooks = {setup, readOrders, writeOrder, iterationForTest, handleSummary};';

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
                id: String(50001 + company * 100 + slot), initial_status: 'ABERTO',
            })),
        })),
    };
}

function response(status, body, duration = 50) {
    return {
        status,
        timings: {duration},
        json: field => {
            const parsed = typeof body === 'string' ? JSON.parse(body) : body;
            return field ? parsed[field] : parsed;
        },
    };
}

function rejection(overrides = {}) {
    return response(503, {
        type: 'urn:tcc:problem:database-capacity',
        code: 'DATABASE_CAPACITY_EXCEEDED',
        operationApplied: false,
        ...overrides,
    }, 5000);
}

function readResponse() {
    return response(200, {page: 0, size: 20, totalElements: 20000, totalPages: 1000, content: Array(20).fill({})});
}

function runner(responses = [], overrides = {}) {
    const metrics = new Map();
    const requests = [];
    let currentTime = 1000000;
    class Counter {
        constructor(name) {
            this.name = name;
        }
        add(value) {
            const count = metrics.get(this.name)?.values.count || 0;
            metrics.set(this.name, {values: {count: count + value}});
        }
    }
    class Trend {
        constructor(name) {
            this.name = name;
        }
        add(value) {
            const samples = [...(metrics.get(this.name)?.samples || []), value].sort((left, right) => left - right);
            const sum = samples.reduce((total, sample) => total + sample, 0);
            metrics.set(this.name, {
                samples,
                values: {avg: sum / samples.length, min: samples[0], med: samples[Math.floor(samples.length / 2)],
                    max: samples.at(-1), 'p(95)': samples.at(-1), 'p(99)': samples.at(-1)},
            });
        }
    }
    const request = (method, url, body, options) => {
        requests.push({method, url, body, options});
        assert.ok(responses.length > 0, 'Toda chamada HTTP deve ter uma resposta simulada.');
        return responses.shift();
    };
    const context = vm.createContext({
        __ENV: {BASE_URL: 'http://localhost:8080', CACHE_MODE: 'on', PROFILE: '90-10'},
        open: () => JSON.stringify(manifest()),
        Date: class extends Date {
            static now() {
                return currentTime;
            }
        },
        Counter,
        Trend,
        http: {
            get: (url, options) => request('GET', url, null, options),
            patch: (url, body, options) => request('PATCH', url, body, options),
        },
        exec: {vu: {idInTest: 1}, test: {abort: reason => {throw new Error(reason);}}},
        sleep: () => {},
        assignment,
        hash,
        operationFor,
        pageFor: () => 0,
        PROFILES,
        random,
        validateManifest,
        ...overrides,
    });
    vm.runInContext(source, context, {filename: 'experiment.js'});
    const windows = context.hooks.setup();
    currentTime = windows.measurement_start_unix_ms;
    return {
        ...context.hooks,
        selected: assignment(manifest(), 1),
        requests,
        windows,
        metrics,
        summary: customMetrics => {
            currentTime = windows.measurement_end_unix_ms + 1;
            const outputs = context.hooks.handleSummary({setup_data: windows, metrics: customMetrics || Object.fromEntries(metrics)});
            return JSON.parse(outputs['measurement-summary.json']);
        },
    };
}

test('recusa 503 exata mantém o status até uma escrita confirmada e separa os resultados', () => {
    const workload = runner([rejection(), response(200, {status: 'CONFIRMADO'}), response(200, {status: 'CANCELADO'})]);
    workload.writeOrder(workload.selected);
    workload.writeOrder(workload.selected);
    workload.writeOrder(workload.selected);
    assert.deepEqual(workload.requests.map(request => JSON.parse(request.body).status), ['CONFIRMADO', 'CONFIRMADO', 'CANCELADO']);
    const summary = workload.summary();
    assert.equal(summary.schema_version, 2);
    assert.equal(summary.protocol_version, 2);
    assert.equal(summary.valid_for_campaign, true);
    assert.equal(summary.writes, 3);
    assert.equal(summary.write_attempts, 3);
    assert.equal(summary.write_successes, 2);
    assert.equal(summary.write_rejections, 1);
    assert.equal(summary.write_uncertain, 0);
    assert.equal(summary.write_errors, 1);
    assert.equal(summary.errors, 1);
    assert.equal(summary.successful_requests_per_second, 2 / 300);
    assert.equal(summary.throughput_requests_per_second, 3 / 300);
    assert.equal(summary.write_success_latency_ms.max, 50);
    assert.equal(summary.write_latency_ms.max, 5000);
});

test('rejeição segura avança a proporção de tentativas sem repetir artificialmente a mesma operação', () => {
    const workload = runner([rejection(), readResponse(), response(200, {status: 'CONFIRMADO'})], {
        operationFor: (_, __, iteration) => iteration === 0 ? [true, false, true] : null,
    });
    workload.iterationForTest(workload.windows);
    workload.iterationForTest(workload.windows);
    workload.iterationForTest(workload.windows);
    assert.deepEqual(workload.requests.map(request => request.method), ['PATCH', 'GET', 'PATCH']);
    assert.equal(workload.summary().read_attempts, 1);
});

test('503 genérico, marca incompleta, timeout e 500 de escrita continuam abortando', () => {
    const responses = [response(503, {}), rejection({operationApplied: true}), rejection({operationApplied: 'false'}),
        rejection({code: 'OTHER'}), rejection({type: 'about:blank'}), response(503, 'invalid'),
        response(0, ''), response(500, {})];
    for (const failedResponse of responses) {
        const workload = runner([failedResponse]);
        assert.throws(() => workload.writeOrder(workload.selected), /estado persistido incerto/);
        const summary = workload.summary();
        assert.equal(summary.valid_for_campaign, false);
        assert.equal(summary.write_rejections, 0);
        assert.equal(summary.write_uncertain, 1);
        assert.equal(summary.write_errors, 1);
    }
});

test('HTTP 200 com status incorreto ou JSON inválido invalida o contrato de escrita', () => {
    for (const invalid of [response(200, {status: 'ABERTO'}), response(200, 'invalid')]) {
        const workload = runner([invalid]);
        assert.throws(() => workload.writeOrder(workload.selected), /estado persistido incerto/);
        const summary = workload.summary();
        assert.equal(summary.response_contract_errors, 1);
        assert.equal(summary.write_uncertain, 1);
        assert.equal(summary.valid, false);
    }
});

test('leituras distinguem sucesso, rejeição de admissão e outros erros sem ocultá-los', () => {
    const workload = runner([readResponse(), rejection(), response(500, {})]);
    workload.readOrders(workload.windows, workload.selected, true);
    workload.readOrders(workload.windows, workload.selected, true);
    workload.readOrders(workload.windows, workload.selected, true);
    const summary = workload.summary();
    assert.equal(summary.valid_for_campaign, true);
    assert.equal(summary.reads, 3);
    assert.equal(summary.read_successes, 1);
    assert.equal(summary.read_rejections, 1);
    assert.equal(summary.read_errors, 2);
    assert.equal(summary.read_success_latency_ms.max, 50);
    assert.equal(summary.read_latency_ms.max, 5000);
    assert.equal(summary.write_success_latency_ms, null);
});

test('resumo utiliza o contador agregado para falhas de escrita de outros contextos VU', () => {
    const summaryContext = runner();
    const summary = summaryContext.summary({
        measurement_writes: {values: {count: 1}},
        measurement_write_errors: {values: {count: 1}},
        measurement_write_uncertain: {values: {count: 1}},
    });
    assert.equal(summary.write_uncertain, 1);
    assert.equal(summary.valid_for_campaign, false);
});

test('saturação total de escritas é mensurável com zero sucesso e latência de sucesso ausente', () => {
    const workload = runner([rejection(), rejection()]);
    workload.writeOrder(workload.selected);
    workload.writeOrder(workload.selected);
    const summary = workload.summary();
    assert.equal(summary.valid_for_campaign, true);
    assert.equal(summary.successes, 0);
    assert.equal(summary.successful_requests_per_second, 0);
    assert.equal(summary.error_ratio, 1);
    assert.equal(summary.write_success_latency_ms, null);
    assert.equal(summary.write_latency_ms.max, 5000);
});

test('contrato inválido de leitura continua abortando', () => {
    const workload = runner([response(200, {page: 1})]);
    assert.throws(() => workload.readOrders(workload.windows, workload.selected, true), /viola o contrato/);
    assert.equal(workload.summary().valid_for_campaign, false);
});
