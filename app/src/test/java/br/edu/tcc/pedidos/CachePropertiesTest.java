package br.edu.tcc.pedidos;

import static org.assertj.core.api.Assertions.assertThat;

import br.edu.tcc.pedidos.config.CacheProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class CachePropertiesTest {

    @Test
    void cacheHabilitadoExigeSenhaNaoVazia() {
        assertThat(configuracao(true, null).isPasswordConfigured()).isFalse();
        assertThat(configuracao(true, "").isPasswordConfigured()).isFalse();
        assertThat(configuracao(true, "senha-cache").isPasswordConfigured()).isTrue();
        assertThat(configuracao(true, "   ").isPasswordConfigured()).isTrue();
    }

    @Test
    void cacheDesabilitadoDispensaSenha() {
        assertThat(configuracao(false, null).isPasswordConfigured()).isTrue();
        assertThat(configuracao(false, "").isPasswordConfigured()).isTrue();
        assertThat(configuracao(false, "senha-cache").isPasswordConfigured()).isTrue();
    }

    @Test
    void duracoesRespeitamLimitesDeTtlETimeout() {
        assertThat(configuracaoDuracoes(Duration.ofMillis(1), Duration.ofMillis(1)).isDurationsValid()).isTrue();
        assertThat(configuracaoDuracoes(Duration.ofHours(1), Duration.ofSeconds(5)).isDurationsValid()).isTrue();
        assertThat(configuracaoDuracoes(Duration.ZERO, Duration.ofMillis(1)).isDurationsValid()).isFalse();
        assertThat(configuracaoDuracoes(Duration.ofMillis(1), Duration.ZERO).isDurationsValid()).isFalse();
        assertThat(configuracaoDuracoes(Duration.ofHours(1).plusMillis(1), Duration.ofSeconds(5))
                .isDurationsValid()).isFalse();
        assertThat(configuracaoDuracoes(Duration.ofHours(1), Duration.ofSeconds(5).plusMillis(1))
                .isDurationsValid()).isFalse();
        assertThat(configuracaoDuracoes(null, Duration.ofSeconds(1)).isDurationsValid()).isFalse();
        assertThat(configuracaoDuracoes(Duration.ofMinutes(1), null).isDurationsValid()).isFalse();
    }

    private CacheProperties configuracao(boolean habilitado, String senha) {
        return new CacheProperties(habilitado, "tcc:test", Duration.ofMinutes(1), Duration.ofMillis(200),
                "localhost", 6379, "tcc_app", senha);
    }

    private CacheProperties configuracaoDuracoes(Duration ttl, Duration timeout) {
        return new CacheProperties(true, "tcc:test", ttl, timeout, "localhost", 6379, "tcc_app", "senha-cache");
    }
}
