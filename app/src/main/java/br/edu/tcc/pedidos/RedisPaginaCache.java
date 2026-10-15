package br.edu.tcc.pedidos;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import org.slf4j.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import static br.edu.tcc.pedidos.Contratos.PaginaPedidos;

public class RedisPaginaCache implements PaginaCache {
    private static final Logger LOG = LoggerFactory.getLogger(RedisPaginaCache.class);
    private static final DefaultRedisScript<String> GENERATION = script("generation", String.class);
    private static final DefaultRedisScript<String> READ = script("read-page", String.class);
    private static final DefaultRedisScript<Long> WRITE = script("write-page", Long.class);
    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final CacheProperties config;
    private final Counter hit, miss, fallback, error, invalidation, discarded;
    private final Map<Long, Object> pending = new ConcurrentHashMap<>();
    private final AtomicLong nextWarning = new AtomicLong();

    public RedisPaginaCache(StringRedisTemplate redis, ObjectMapper mapper, CacheProperties config, MeterRegistry meters) {
        this.redis = redis; this.mapper = mapper; this.config = config;
        hit = meters.counter("tcc.cache.requests", "result", "hit");
        miss = meters.counter("tcc.cache.requests", "result", "miss");
        fallback = meters.counter("tcc.cache.requests", "result", "fallback");
        error = meters.counter("tcc.cache.errors");
        invalidation = meters.counter("tcc.cache.invalidations");
        discarded = meters.counter("tcc.cache.discarded_writes");
    }
    private static <T> DefaultRedisScript<T> script(String name, Class<T> type) {
        var script = new DefaultRedisScript<T>();
        script.setLocation(new ClassPathResource("cache/" + name + ".lua"));
        script.setResultType(type);
        return script;
    }
    private String base(long tenant) { return config.namespace() + ":tenant:{" + tenant + "}:pedidos:"; }
    private String generationKey(long tenant) { return base(tenant) + "generation"; }
    private String pageKey(long tenant, String generation, int page, int size) {
        return base(tenant) + generation + ":page:" + page + ":size:" + size;
    }
    @Override
    public PaginaPedidos buscarOuCarregar(long tenant, int page, int size, Supplier<PaginaPedidos> banco) {
        String generation;
        String key;
        try {
            if (!repair(tenant)) {
                throw new InvalidacaoPendente();
            }
            generation = redis.execute(GENERATION, List.of(generationKey(tenant)), UUID.randomUUID().toString());
            if (generation == null) throw new IllegalStateException("Redis não retornou a versão do cache");
            key = pageKey(tenant, generation, page, size);
            var cached = redis.execute(READ, List.of(generationKey(tenant), key), generation);
            if (cached != null) {
                try {
                    var result = mapper.readValue(cached, PaginaPedidos.class);
                    if (result == null || result.content() == null || result.page() != page || result.size() != size)
                        throw new IllegalArgumentException("Página de cache inválida");
                    hit.increment();
                    return result;
                } catch (JsonProcessingException | IllegalArgumentException ex) {
                    failed(ex); // Recarrega e substitui somente esta página após a consulta.
                }
            }
        } catch (InvalidacaoPendente ex) {
            fallback.increment();
            return banco.get();
        } catch (RuntimeException ex) {
            failed(ex);
            fallback.increment();
            return banco.get();
        }
        miss.increment();
        // Exceções de negócio/banco não são capturadas como falhas do Redis.
        var result = banco.get();
        try {
            if (pending.containsKey(tenant)) {
                discarded.increment();
            } else {
                Long stored = redis.execute(WRITE, List.of(generationKey(tenant), key), generation,
                        mapper.writeValueAsString(result), Long.toString(config.ttl().toMillis()));
                if (!Long.valueOf(1).equals(stored)) discarded.increment();
            }
        } catch (RuntimeException | JsonProcessingException ex) { failed(ex); }
        return result;
    }
    @Override
    public void invalidar(long tenant) {
        // Marca antes da tentativa. Remove apenas o marcador que esta tentativa resolveu.
        var marker = new Object();
        pending.put(tenant, marker);
        try {
            rotate(tenant);
            pending.remove(tenant, marker);
        } catch (RuntimeException ex) { failed(ex); }
    }
    private boolean repair(long tenant) {
        Object marker = pending.get(tenant);
        if (marker == null) return true;
        rotate(tenant);
        pending.remove(tenant, marker);
        return !pending.containsKey(tenant);
    }
    private void rotate(long tenant) {
        // Cada tentativa usa um UUID novo: retries não ressuscitam versões antigas.
        redis.opsForValue().set(generationKey(tenant), UUID.randomUUID().toString());
        invalidation.increment();
    }
    private static class InvalidacaoPendente extends RuntimeException {}

    private void failed(Exception ex) {
        error.increment();
        long now = System.nanoTime();
        long next = nextWarning.get();
        if (now >= next && nextWarning.compareAndSet(next, now + java.time.Duration.ofSeconds(30).toNanos()))
            LOG.warn("Cache indisponível ou inválido ({}); operação seguirá pelo PostgreSQL.", ex.getClass().getSimpleName());
    }
}
