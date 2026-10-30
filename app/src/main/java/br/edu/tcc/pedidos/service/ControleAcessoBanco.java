package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.exception.CapacidadeBancoExcedidaException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ControleAcessoBanco {

    private final Semaphore vagas;
    private final long esperaMaximaMillis;

    public ControleAcessoBanco(
            @Value("${spring.datasource.hikari.maximum-pool-size}") int operacoesSimultaneas,
            @Value("${spring.datasource.hikari.connection-timeout}") long esperaMaximaMillis) {
        if (operacoesSimultaneas < 1 || esperaMaximaMillis < 1) {
            throw new IllegalArgumentException("Capacidade e tempo de espera devem ser positivos");
        }

        this.vagas = new Semaphore(operacoesSimultaneas, true);
        this.esperaMaximaMillis = esperaMaximaMillis;
    }

    public <T> T executar(Supplier<T> operacao) {
        boolean entradaPermitida;
        try {
            entradaPermitida = vagas.tryAcquire(esperaMaximaMillis, TimeUnit.MILLISECONDS);
        } catch (InterruptedException interrupcao) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Espera por acesso ao banco interrompida", interrupcao);
        }

        if (!entradaPermitida) {
            throw new CapacidadeBancoExcedidaException();
        }

        try {
            return operacao.get();
        } finally {
            vagas.release();
        }
    }
}
