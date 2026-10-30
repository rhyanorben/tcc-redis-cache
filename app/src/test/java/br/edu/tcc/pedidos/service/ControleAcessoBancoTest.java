package br.edu.tcc.pedidos.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import br.edu.tcc.pedidos.exception.CapacidadeBancoExcedidaException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class ControleAcessoBancoTest {

    @Test
    void rejeitaAntesDeExecutarOperacaoQuandoTempoDeEsperaAcaba() throws Exception {
        ControleAcessoBanco controle = new ControleAcessoBanco(1, 50);
        CountDownLatch vagaOcupada = new CountDownLatch(1);
        CountDownLatch liberarVaga = new CountDownLatch(1);
        AtomicBoolean operacaoExecutada = new AtomicBoolean();
        Thread ocupante = new Thread(() -> controle.executar(() -> {
            vagaOcupada.countDown();
            aguardar(liberarVaga);
            return null;
        }));
        ocupante.start();

        try {
            assertThat(vagaOcupada.await(5, TimeUnit.SECONDS)).isTrue();
            assertThatThrownBy(() -> controle.executar(() -> {
                operacaoExecutada.set(true);
                return null;
            })).isInstanceOf(CapacidadeBancoExcedidaException.class);
            assertThat(operacaoExecutada).isFalse();
        } finally {
            liberarVaga.countDown();
            ocupante.join(5000);
        }

        assertThat(controle.executar(() -> "recuperado")).isEqualTo("recuperado");
    }

    @Test
    void admiteOperacoesNaOrdemDeEspera() throws Exception {
        ControleAcessoBanco controle = new ControleAcessoBanco(1, 5000);
        CountDownLatch vagaOcupada = new CountDownLatch(1);
        CountDownLatch liberarVaga = new CountDownLatch(1);
        List<Integer> ordem = Collections.synchronizedList(new ArrayList<>());
        List<Thread> fila = new ArrayList<>();
        AtomicReference<Throwable> falha = new AtomicReference<>();
        Thread ocupante = new Thread(() -> controle.executar(() -> {
            vagaOcupada.countDown();
            aguardar(liberarVaga);
            return null;
        }));
        ocupante.start();

        try {
            assertThat(vagaOcupada.await(5, TimeUnit.SECONDS)).isTrue();
            for (int indice = 1; indice <= 3; indice++) {
                int identificador = indice;
                Thread concorrente = new Thread(() -> {
                    try {
                        controle.executar(() -> ordem.add(identificador));
                    } catch (Throwable erro) {
                        falha.set(erro);
                    }
                });
                fila.add(concorrente);
                concorrente.start();
                await().atMost(Duration.ofSeconds(2))
                        .until(() -> concorrente.getState() == Thread.State.TIMED_WAITING);
            }
        } finally {
            liberarVaga.countDown();
            ocupante.join(5000);
            for (Thread concorrente : fila) {
                concorrente.join(5000);
                assertThat(concorrente.isAlive()).isFalse();
            }
        }

        assertThat(falha.get()).isNull();
        assertThat(ordem).containsExactly(1, 2, 3);
    }

    @Test
    void liberaVagaDepoisDaFalhaDaOperacao() {
        ControleAcessoBanco controle = new ControleAcessoBanco(1, 50);
        IllegalStateException falha = new IllegalStateException("Falha na operação");

        assertThatThrownBy(() -> controle.executar(() -> {
            throw falha;
        })).isSameAs(falha);
        assertThat(controle.executar(() -> "outra operação")).isEqualTo("outra operação");
    }

    @Test
    void interrupcaoPreservaSinalSemExecutarOuLiberarVagaDeOutroPedido() throws Exception {
        ControleAcessoBanco controle = new ControleAcessoBanco(1, 5000);
        CountDownLatch vagaOcupada = new CountDownLatch(1);
        CountDownLatch liberarVaga = new CountDownLatch(1);
        AtomicBoolean executada = new AtomicBoolean();
        AtomicBoolean interrompida = new AtomicBoolean();
        AtomicReference<Throwable> falha = new AtomicReference<>();
        Thread ocupante = new Thread(() -> controle.executar(() -> {
            vagaOcupada.countDown();
            aguardar(liberarVaga);
            return null;
        }));
        Thread concorrente = new Thread(() -> {
            try {
                controle.executar(() -> executada.getAndSet(true));
            } catch (Throwable erro) {
                falha.set(erro);
                interrompida.set(Thread.currentThread().isInterrupted());
            }
        });
        ocupante.start();

        try {
            assertThat(vagaOcupada.await(5, TimeUnit.SECONDS)).isTrue();
            concorrente.start();
            await().atMost(Duration.ofSeconds(2))
                    .until(() -> concorrente.getState() == Thread.State.TIMED_WAITING);
            concorrente.interrupt();
            concorrente.join(5000);
            assertThat(falha.get()).isInstanceOf(IllegalStateException.class);
            assertThat(interrompida).isTrue();
            assertThat(executada).isFalse();
        } finally {
            liberarVaga.countDown();
            ocupante.join(5000);
            concorrente.join(5000);
        }

        assertThat(controle.executar(() -> "recuperado")).isEqualTo("recuperado");
    }

    private void aguardar(CountDownLatch liberarVaga) {
        try {
            if (!liberarVaga.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Tempo de espera excedido");
            }
        } catch (InterruptedException interrupcao) {
            Thread.currentThread().interrupt();
            throw new AssertionError(interrupcao);
        }
    }
}
