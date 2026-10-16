package br.edu.tcc.pedidos.config;

import br.edu.tcc.pedidos.cache.PaginaCache;
import br.edu.tcc.pedidos.cache.PaginaCacheDesabilitado;
import br.edu.tcc.pedidos.cache.RedisPaginaCache;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.lettuce.core.ClientOptions;
import io.lettuce.core.SocketOptions;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CacheProperties.class)
public class CacheConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "false", matchIfMissing = true)
    PaginaCache semCache() {
        return new PaginaCacheDesabilitado();
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    LettuceConnectionFactory redisConnectionFactory(CacheProperties properties) {
        RedisStandaloneConfiguration redisConfiguration =
                new RedisStandaloneConfiguration(properties.host(), properties.port());
        redisConfiguration.setUsername(properties.username());
        redisConfiguration.setPassword(properties.password());

        SocketOptions socketOptions = SocketOptions.builder()
                .connectTimeout(properties.timeout())
                .build();
        ClientOptions clientOptions = ClientOptions.builder()
                .disconnectedBehavior(ClientOptions.DisconnectedBehavior.REJECT_COMMANDS)
                .socketOptions(socketOptions)
                .build();
        LettuceClientConfiguration clientConfiguration = LettuceClientConfiguration.builder()
                .commandTimeout(properties.timeout())
                .clientOptions(clientOptions)
                .build();

        return new LettuceConnectionFactory(redisConfiguration, clientConfiguration);
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    StringRedisTemplate redisTemplate(LettuceConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.cache", name = "enabled", havingValue = "true")
    RedisPaginaCache comCache(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            CacheProperties properties,
            MeterRegistry meterRegistry) {
        return new RedisPaginaCache(redisTemplate, objectMapper, properties, meterRegistry);
    }
}
