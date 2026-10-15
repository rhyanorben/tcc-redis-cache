package br.edu.tcc.pedidos;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

final class MetricasCache {

    private final Counter acertos;
    private final Counter ausencias;
    private final Counter consultasAoBancoPorFalha;
    private final Counter falhas;
    private final Counter invalidacoes;
    private final Counter gravacoesDescartadas;

    MetricasCache(MeterRegistry meterRegistry) {
        acertos = meterRegistry.counter("tcc.cache.requests", "result", "hit");
        ausencias = meterRegistry.counter("tcc.cache.requests", "result", "miss");
        consultasAoBancoPorFalha = meterRegistry.counter("tcc.cache.requests", "result", "fallback");
        falhas = meterRegistry.counter("tcc.cache.errors");
        invalidacoes = meterRegistry.counter("tcc.cache.invalidations");
        gravacoesDescartadas = meterRegistry.counter("tcc.cache.discarded_writes");
    }

    void registrarAcerto() {
        acertos.increment();
    }

    void registrarAusencia() {
        ausencias.increment();
    }

    void registrarConsultaAoBancoPorFalha() {
        consultasAoBancoPorFalha.increment();
    }

    void registrarFalha() {
        falhas.increment();
    }

    void registrarInvalidacao() {
        invalidacoes.increment();
    }

    void registrarGravacaoDescartada() {
        gravacoesDescartadas.increment();
    }
}
