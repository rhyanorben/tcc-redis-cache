package br.edu.tcc.pedidos;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties("app.cache")
@Validated
public record CacheProperties(
        boolean enabled,
        @Pattern(regexp = "tcc:[A-Za-z0-9:_-]{1,60}") String namespace,
        @NotNull Duration ttl,
        @NotNull Duration timeout,
        @NotBlank String host,
        @Min(1) @Max(65535) int port,
        @NotBlank String username,
        String password) {

    @AssertTrue(message = "TTL deve ficar entre 1ms e 1h e timeout entre 1ms e 5s")
    public boolean isDurationsValid() {
        return duracaoValida(ttl, Duration.ofHours(1))
                && duracaoValida(timeout, Duration.ofSeconds(5));
    }

    @AssertTrue(message = "REDIS_PASSWORD é obrigatória quando o cache está habilitado")
    public boolean isPasswordConfigured() {
        return !enabled || (password != null && !password.isBlank());
    }

    private boolean duracaoValida(Duration duracao, Duration limiteSuperior) {
        return duracao != null
                && duracao.toMillis() >= 1
                && duracao.compareTo(limiteSuperior) <= 0;
    }
}
