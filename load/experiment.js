import http from 'k6/http';
import exec from 'k6/execution';
import {sleep} from 'k6';
import {Counter, Trend} from 'k6/metrics';
import {assignment, hash, operationFor, PROFILES, random, validateManifest} from './workload.js';
import {PaginationJourney, validateNavigation} from './navigation.js';

const phase = __ENV.PHASE || 'measurement';
const profile = __ENV.PROFILE || '100-0';
const virtualUsers = Number(__ENV.VUS || 25);
const seed = __ENV.SEED || '20261017';
const cacheMode = __ENV.CACHE_MODE;
const runId = __ENV.RUN_ID || 'manual';
const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '');
const allowedUrl = /^http:\/\/(10\.10\.10\.10|10\.20\.20\.10|localhost|127\.0\.0\.1)(:[0-9]{1,5})?$/;
const smokeSeconds = __ENV.SMOKE_TEST_SECONDS ? Number(__ENV.SMOKE_TEST_SECONDS) : 0;
if (!allowedUrl.test(baseUrl) || !['warmup', 'measurement', 'full'].includes(phase)
        || !Object.prototype.hasOwnProperty.call(PROFILES, profile)
        || ![25, 50, 100, 250, 500].includes(virtualUsers)
        || !['on', 'off'].includes(cacheMode)) {
    throw new Error('Destino, PHASE, PROFILE, VUS ou CACHE_MODE inválidos.');
}
if (smokeSeconds !== 0 && (!Number.isInteger(smokeSeconds) || smokeSeconds < 1 || smokeSeconds > 10
        || phase !== 'measurement' || !/^http:\/\/(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$/.test(baseUrl))) {
    throw new Error('Smoke exige localhost, PHASE=measurement e duração de 1 a 10 segundos.');
}
const manifest = JSON.parse(open(__ENV.MANIFEST || './manifesto.json'));
validateManifest(manifest);
const navigationConfig = JSON.parse(open('./navigation.json'));
validateNavigation(navigationConfig);
const warmupMs = phase === 'full' || phase === 'warmup' ? 120000 : 0;
const measurementMs = phase === 'warmup' ? 0 : (smokeSeconds || 300) * 1000;
const startupMs = 3000;
const readCount = new Counter('measurement_reads');
const writeCount = new Counter('measurement_writes');
const readErrors = new Counter('measurement_read_errors');
const writeErrors = new Counter('measurement_write_errors');
const readSuccesses = new Counter('measurement_read_successes');
const writeSuccesses = new Counter('measurement_write_successes');
const readRejections = new Counter('measurement_read_rejections');
const writeRejections = new Counter('measurement_write_rejections');
const writeUncertain = new Counter('measurement_write_uncertain');
const readLatency = new Trend('measurement_read_duration_ms', true);
const writeLatency = new Trend('measurement_write_duration_ms', true);
const readSuccessLatency = new Trend('measurement_read_success_duration_ms', true);
const writeSuccessLatency = new Trend('measurement_write_success_duration_ms', true);
const warmupErrors = new Counter('warmup_read_errors');
const warmupReads = new Counter('warmup_reads');
const contractErrors = new Counter('response_contract_errors');
const forwardVisits = new Counter('measurement_forward_visits');
const reverseVisits = new Counter('measurement_reverse_visits');
const pageClasses = ['first', 'intermediate', 'last'];
const paginationReads = Object.fromEntries(pageClasses.map(name => [name, new Counter(`measurement_${name}_page_reads`)]));
const paginationErrors = Object.fromEntries(pageClasses.map(name => [name, new Counter(`measurement_${name}_page_errors`)]));
const paginationLatency = Object.fromEntries(pageClasses.map(name => [name, new Trend(`measurement_${name}_page_duration_ms`, true)]));
let writeIndex = 0;
let iteration = 0;
let operationBlock = [];
let workloadRandom;
let warmupRandom;
let measurementJourney;
let warmupJourney;

export const options = {
    scenarios: {
        experiment: {
            executor: 'constant-vus',
            vus: virtualUsers,
            duration: `${(startupMs + warmupMs + measurementMs) / 1000}s`,
            gracefulStop: '15s',
        },
    },
    discardResponseBodies: false,
    maxRedirects: 0,
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
    systemTags: ['method', 'name', 'status', 'scenario'],
};

export function setup() {
    const start = Date.now() + startupMs;
    return {
        warmup_start_unix_ms: warmupMs > 0 ? start : null,
        measurement_start_unix_ms: measurementMs > 0 ? start + warmupMs : null,
        measurement_end_unix_ms: measurementMs > 0 ? start + warmupMs + measurementMs : null,
        workload_start_unix_ms: start,
        workload_end_unix_ms: start + warmupMs + measurementMs,
    };
}

function databaseCapacityRejected(response) {
    if (response.status !== 503) {
        return false;
    }
    try {
        const problem = response.json();
        return problem.type === 'urn:tcc:problem:database-capacity'
            && problem.code === 'DATABASE_CAPACITY_EXCEEDED' && problem.operationApplied === false;
    } catch (error) {
        return false;
    }
}

function readOrders(data, selected, measured) {
    initializeWorkload(selected);
    const journey = measured ? measurementJourney : warmupJourney;
    const navigation = journey.current();
    const page = navigation.page;
    if (measured && navigation.newVisit) {
        (navigation.direction === 'forward' ? forwardVisits : reverseVisits).add(1);
    }
    const url = `${baseUrl}/api/pedidos?page=${page}&size=20&sort=criadoEm,desc&sort=id,desc`;
    const response = http.get(url, {
        headers: {tenantId: selected.company.tenant_id},
        timeout: '10s',
        tags: {name: 'GET /api/pedidos', operation: 'read', phase: measured ? 'measurement' : 'warmup'},
    });
    let valid = response.status === 200;
    if (valid) {
        try {
            const body = response.json();
            valid = body.page === page && body.size === 20 && body.totalElements === 20000
                && body.totalPages === 1000 && Array.isArray(body.content) && body.content.length === 20;
        } catch (error) {
            valid = false;
        }
    }
    if (measured) {
        paginationReads[navigation.pageClass].add(1);
        paginationErrors[navigation.pageClass].add(valid ? 0 : 1);
        paginationLatency[navigation.pageClass].add(response.timings.duration);
        readCount.add(1);
        readErrors.add(valid ? 0 : 1);
        readLatency.add(response.timings.duration);
        if (valid) {
            readSuccesses.add(1);
            readSuccessLatency.add(response.timings.duration);
        } else if (databaseCapacityRejected(response)) {
            readRejections.add(1);
        }
    } else {
        warmupReads.add(1);
        warmupErrors.add(valid ? 0 : 1);
    }
    if (response.status === 200 && !valid) {
        contractErrors.add(1);
        exec.test.abort('Resposta HTTP 200 viola o contrato da listagem; invalide esta execução.');
    }
    if (valid) {
        journey.completed();
    }
}

function writeOrder(selected) {
    const status = writeIndex % 2 === 0 ? 'CONFIRMADO' : 'CANCELADO';
    const response = http.patch(`${baseUrl}/api/pedidos/${selected.orderId}/status`, JSON.stringify({status}), {
        headers: {tenantId: selected.company.tenant_id, 'Content-Type': 'application/json'},
        timeout: '10s',
        tags: {name: 'PATCH /api/pedidos/:id/status', operation: 'write', phase: 'measurement'},
    });
    let valid = response.status === 200;
    if (valid) {
        try {
            valid = response.json('status') === status;
        } catch (error) {
            valid = false;
        }
    }
    writeCount.add(1);
    writeErrors.add(valid ? 0 : 1);
    writeLatency.add(response.timings.duration);
    if (valid) {
        writeSuccesses.add(1);
        writeSuccessLatency.add(response.timings.duration);
        writeIndex += 1;
    } else if (databaseCapacityRejected(response)) {
        writeRejections.add(1);
    } else {
        writeUncertain.add(1);
        if (response.status === 200) {
            contractErrors.add(1);
        }
        exec.test.abort('PATCH falhou: estado persistido incerto; restaure a base e invalide esta execução.');
    }
}

function initializeWorkload(selected) {
    const virtualUser = exec.vu.idInTest;
    if (!workloadRandom) {
        workloadRandom = random(hash(`${seed}|measurement|${virtualUser}`));
        warmupRandom = random(hash(`${seed}|warmup|${virtualUser}`));
        measurementJourney = new PaginationJourney(
            random(hash(`${seed}|navigation|measurement|${virtualUser}`)),
            selected.company.total_orders / manifest.page_size, navigationConfig);
        warmupJourney = new PaginationJourney(
            warmupRandom, selected.company.total_orders / manifest.page_size, navigationConfig);
    }
}

export default function (data) {
    const now = Date.now();
    if (now < data.workload_start_unix_ms) {
        sleep((data.workload_start_unix_ms - now) / 1000);
        return;
    }
    if (now >= data.workload_end_unix_ms) {
        sleep(0.1);
        return;
    }
    const virtualUser = exec.vu.idInTest;
    const selected = assignment(manifest, virtualUser);
    initializeWorkload(selected);
    const measured = measurementMs > 0 && now >= data.measurement_start_unix_ms;
    if (!measured) {
        readOrders(data, selected, false);
        return;
    }
    const replacement = operationFor(workloadRandom, PROFILES[profile], iteration);
    if (replacement) {
        operationBlock = replacement;
    }
    if (operationBlock[iteration % 100]) {
        writeOrder(selected);
    } else {
        readOrders(data, selected, true);
    }
    iteration += 1;
}

export function handleSummary(data) {
    const windows = data.setup_data || {};
    const count = name => data.metrics[name] ? data.metrics[name].values.count : 0;
    const latency = name => data.metrics[name] ? data.metrics[name].values : null;
    const reads = count('measurement_reads');
    const writes = count('measurement_writes');
    const errors = count('measurement_read_errors') + count('measurement_write_errors');
    const successfulReads = count('measurement_read_successes');
    const successfulWrites = count('measurement_write_successes');
    const rejectedReads = count('measurement_read_rejections');
    const rejectedWrites = count('measurement_write_rejections');
    const uncertainWrites = count('measurement_write_uncertain');
    const successfulRequests = successfulReads + successfulWrites;
    const elapsed = Math.max(0, Math.min(measurementMs, Date.now() - (windows.measurement_start_unix_ms || Date.now())));
    const completed = measurementMs > 0 && elapsed >= measurementMs;
    const summary = {
        schema_version: 2,
        protocol_version: 3,
        navigation: {
            config: navigationConfig,
            forward_visits: count('measurement_forward_visits'),
            reverse_visits: count('measurement_reverse_visits'),
            reads: Object.fromEntries(pageClasses.map(name => [name, count(`measurement_${name}_page_reads`)])),
            errors: Object.fromEntries(pageClasses.map(name => [name, count(`measurement_${name}_page_errors`)])),
            latency_ms: Object.fromEntries(pageClasses.map(name => [name, latency(`measurement_${name}_page_duration_ms`)])),
        },
        scope: 'measurement_only',
        run_id: runId,
        phase,
        profile,
        virtual_users: virtualUsers,
        seed,
        cache_mode: cacheMode,
        active_companies: 25,
        page_size: 20,
        measurement_start_unix_ms: windows.measurement_start_unix_ms || null,
        measurement_end_unix_ms: windows.measurement_end_unix_ms || null,
        measurement_completed_unix_ms: Date.now(),
        nominal_measurement_seconds: measurementMs / 1000,
        valid: phase === 'warmup' ? count('warmup_reads') > 0 && count('response_contract_errors') === 0
            : completed && uncertainWrites === 0 && count('response_contract_errors') === 0,
        smoke_test: smokeSeconds > 0,
        valid_for_campaign: phase !== 'warmup' && smokeSeconds === 0 && completed
            && uncertainWrites === 0 && count('response_contract_errors') === 0,
        reads,
        writes,
        requests: reads + writes,
        read_attempts: reads,
        write_attempts: writes,
        attempts: reads + writes,
        read_successes: successfulReads,
        write_successes: successfulWrites,
        successes: successfulRequests,
        read_rejections: rejectedReads,
        write_rejections: rejectedWrites,
        rejections: rejectedReads + rejectedWrites,
        write_uncertain: uncertainWrites,
        errors,
        read_errors: count('measurement_read_errors'),
        write_errors: count('measurement_write_errors'),
        warmup_read_errors: count('warmup_read_errors'),
        warmup_reads: count('warmup_reads'),
        response_contract_errors: count('response_contract_errors'),
        throughput_requests_per_second: measurementMs > 0 ? (reads + writes) / (measurementMs / 1000) : null,
        successful_requests_per_second: measurementMs > 0 ? successfulRequests / (measurementMs / 1000) : null,
        successful_read_requests_per_second: measurementMs > 0 ? successfulReads / (measurementMs / 1000) : null,
        successful_write_requests_per_second: measurementMs > 0 ? successfulWrites / (measurementMs / 1000) : null,
        error_ratio: reads + writes > 0 ? errors / (reads + writes) : null,
        observed_write_ratio: reads + writes > 0 ? writes / (reads + writes) : null,
        read_latency_ms: latency('measurement_read_duration_ms'),
        write_latency_ms: latency('measurement_write_duration_ms'),
        read_success_latency_ms: latency('measurement_read_success_duration_ms'),
        write_success_latency_ms: latency('measurement_write_success_duration_ms'),
    };
    return {
        [__ENV.SUMMARY_PATH || 'measurement-summary.json']: `${JSON.stringify(summary, null, 2)}\n`,
        stdout: `${JSON.stringify({run_id: runId, valid: summary.valid, reads, writes, errors})}\n`,
    };
}
