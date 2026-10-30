import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {PaginationJourney, validateNavigation} from '../navigation.js';
import {hash, random} from '../workload.js';

const config = JSON.parse(readFileSync(new URL('../navigation.json', import.meta.url)));

function fixed(values) {
    let index = 0;
    return () => values[index++ % values.length];
}

function pages(journey, count) {
    return Array.from({length: count}, () => {
        const current = journey.current();
        journey.completed();
        return current;
    });
}

test('visita progressiva começa em zero, avança e reinicia ao encerrar', () => {
    const journey = new PaginationJourney(fixed([0.2]), 1000, {...config, local_return_ratio: 0});
    const visits = pages(journey, 11);
    assert.deepEqual(visits.map(value => value.page), [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0]);
    assert.deepEqual(visits.filter(value => value.newVisit).map(value => value.page), [0, 0, 0]);
    assert.ok(visits.every(value => value.direction === 'forward'));
});

test('visita regressiva abre zero, vai à última e retorna sem saltos intermediários', () => {
    const journey = new PaginationJourney(fixed([0.95, 0]), 1000, config);
    const visits = pages(journey, 8);
    assert.deepEqual(visits.map(value => value.page), [0, 999, 998, 997, 0, 999, 998, 997]);
    assert.ok(visits.every(value => value.direction === 'reverse'));
    assert.deepEqual(visits.slice(0, 4).map(value => value.pageClass), ['first', 'last', 'intermediate', 'intermediate']);
});

test('retorno local preserva navegação vizinha e não escolhe páginas aleatórias', () => {
    const journey = new PaginationJourney(fixed([0.2, 0.9, 0.05, 0.8]), 1000, config);
    const visits = pages(journey, 100);
    for (let index = 1; index < visits.length; index += 1) {
        if (visits[index].newVisit) {
            assert.equal(visits[index].page, 0);
        } else {
            assert.equal(Math.abs(visits[index].page - visits[index - 1].page), 1);
        }
    }
    assert.ok(visits.some((value, index) => index > 0 && !value.newVisit && value.page < visits[index - 1].page));
});

test('leitura que falha mantém a página e não conta uma nova visita', () => {
    const journey = new PaginationJourney(fixed([0.2]), 1000, config);
    const first = journey.current();
    const retry = journey.current();
    assert.equal(first.newVisit, true);
    assert.equal(retry.newVisit, false);
    assert.equal(retry.page, first.page);
    journey.completed();
    assert.equal(journey.current().page, 1);
});

test('navegação é reproduzível e mantém aproximadamente 90/10 por visita', () => {
    const left = new PaginationJourney(random(hash('navigation')), 1000, config);
    const right = new PaginationJourney(random(hash('navigation')), 1000, config);
    const visits = pages(left, 100000);
    assert.deepEqual(visits, pages(right, 100000));
    const starts = visits.filter(value => value.newVisit);
    const forward = starts.filter(value => value.direction === 'forward').length / starts.length;
    assert.ok(forward > 0.89 && forward < 0.91);
    assert.ok(visits.every(value => value.page >= 0 && value.page < 1000));
    for (let index = 1; index < visits.length; index += 1) {
        const current = visits[index];
        const previous = visits[index - 1];
        if (current.newVisit) {
            assert.equal(current.page, 0);
        } else if (previous.newVisit && current.direction === 'reverse') {
            assert.equal(current.page, 999);
        } else {
            assert.equal(Math.abs(current.page - previous.page), 1);
        }
    }
});

test('uma ou duas páginas não geram índices negativos ou além do fim', () => {
    for (const total of [1, 2]) {
        const journey = new PaginationJourney(random(3), total, config);
        assert.ok(pages(journey, 1000).every(value => value.page >= 0 && value.page < total));
    }
});

test('rejeita configuração incompleta, direção equiprovável e limites inválidos', () => {
    for (const invalid of [
        {...config, forward_visit_ratio: 0.5},
        {...config, minimum_reads_per_visit: 0},
        {...config, maximum_reads_per_visit: 2},
        {...config, local_return_ratio: NaN},
    ]) {
        assert.throws(() => validateNavigation(invalid));
    }
    assert.throws(() => new PaginationJourney(random(3), 0, config));
});
