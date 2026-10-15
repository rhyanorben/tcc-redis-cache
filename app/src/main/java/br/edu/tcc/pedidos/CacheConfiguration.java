package br.edu.tcc.pedidos;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.lettuce.core.ClientOptions;
import io.lettuce.core.SocketOptions;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.*;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CacheProperties.class)
public class CacheConfiguration {
    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "false", matchIfMissing = true)
    PaginaCache semCache() {
        return new PaginaCache() {
            public Contratos.PaginaPedidos buscarOuCarregar(long tenant, int page, int size,
                    java.util.function.Supplier<Contratos.PaginaPedidos> banco) { return banco.get(); }
            public void invalidar(long tenant) {}
        };
    }
    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    LettuceConnectionFactory redisConnectionFactory(CacheProperties config) {
        var server = new RedisStandaloneConfiguration(config.host(), config.port());
        server.setUsername(config.username());
        server.setPassword(config.password());
        var client = LettuceClientConfiguration.builder().commandTimeout(config.timeout())
                .clientOptions(ClientOptions.builder()
                        .disconnectedBehavior(ClientOptions.DisconnectedBehavior.REJECT_COMMANDS)
                        .socketOptions(SocketOptions.builder().connectTimeout(config.timeout()).build()).build())
                .build();
        return new LettuceConnectionFactory(server, client);
    }
    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    StringRedisTemplate redisTemplate(LettuceConnectionFactory factory) { return new StringRedisTemplate(factory); }

    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    RedisPaginaCache comCache(StringRedisTemplate redis, ObjectMapper mapper, CacheProperties config, MeterRegistry meters) {
        return new RedisPaginaCache(redis, mapper, config, meters);
    }
}
