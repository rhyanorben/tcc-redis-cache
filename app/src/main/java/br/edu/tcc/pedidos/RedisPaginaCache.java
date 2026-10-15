package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public class RedisPaginaCache implements PaginaCache {

    private static final Logger LOGGER = LoggerFactory.getLogger(RedisPaginaCache.class);
    private static final long INTERVALO_ENTRE_AVISOS_NANOS = Duration.ofSeconds(30).toNanos();
    private static final DefaultRedisScript<String> OBTER_VERSAO = carregarScript("generation", String.class);
    private static final DefaultRedisScript<String> LER_PAGINA = carregarScript("read-page", String.class);
    private static final DefaultRedisScript<Long> GRAVAR_PAGINA = carregarScript("write-page", Long.class);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final CacheProperties properties;
    private final MetricasCache metricas;
    private final Map<Long, Object> invalidacoesPendentes = new ConcurrentHashMap<>();
    private final AtomicLong proximoAvisoNanos = new AtomicLong();

    public RedisPaginaCache(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            CacheProperties properties,
            MeterRegistry meterRegistry) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.metricas = new MetricasCache(meterRegistry);
    }

    @Override
    public PaginaPedidos buscarOuCarregar(
            long tenantId,
            int pagina,
            int tamanho,
            Supplier<PaginaPedidos> carregarDoBanco) {
        var leituraCache = tentarLerPagina(tenantId, pagina, tamanho);

        if (leituraCache.isEmpty()) {
            metricas.registrarConsultaAoBancoPorFalha();
            return carregarDoBanco.get();
        }

        var leitura = leituraCache.get();
        if (leitura.paginaArmazenada().isPresent()) {
            metricas.registrarAcerto();
            return leitura.paginaArmazenada().get();
        }

        metricas.registrarAusencia();
        var paginaConsultada = carregarDoBanco.get();
        tentarArmazenarPagina(tenantId, leitura, paginaConsultada);
        return paginaConsultada;
    }

    @Override
    public void invalidar(long tenantId) {
        var marcadorInvalidacao = new Object();
        invalidacoesPendentes.put(tenantId, marcadorInvalidacao);

        try {
            renovarVersao(tenantId);
            invalidacoesPendentes.remove(tenantId, marcadorInvalidacao);
        } catch (RuntimeException exception) {
            registrarFalha(exception);
        }
    }

    private Optional<LeituraCache> tentarLerPagina(long tenantId, int pagina, int tamanho) {
        try {
            if (!repararInvalidacaoPendente(tenantId)) {
                return Optional.empty();
            }

            String versao = obterOuCriarVersao(tenantId);
            String chavePagina = chavePagina(tenantId, versao, pagina, tamanho);
            String jsonPagina = redisTemplate.execute(
                    LER_PAGINA,
                    List.of(chaveVersao(tenantId), chavePagina),
                    versao);
            var paginaArmazenada = deserializarPagina(jsonPagina, pagina, tamanho);

            return Optional.of(new LeituraCache(versao, chavePagina, paginaArmazenada));
        } catch (RuntimeException exception) {
            registrarFalha(exception);
            return Optional.empty();
        }
    }

    private String obterOuCriarVersao(long tenantId) {
        String versao = redisTemplate.execute(
                OBTER_VERSAO,
                List.of(chaveVersao(tenantId)),
                UUID.randomUUID().toString());

        if (versao == null) {
            throw new IllegalStateException("Redis não retornou a versão do cache");
        }

        return versao;
    }

    private Optional<PaginaPedidos> deserializarPagina(String jsonPagina, int pagina, int tamanho) {
        if (jsonPagina == null) {
            return Optional.empty();
        }

        try {
            var paginaArmazenada = objectMapper.readValue(jsonPagina, PaginaPedidos.class);
            if (paginaArmazenada == null
                    || paginaArmazenada.content() == null
                    || paginaArmazenada.page() != pagina
                    || paginaArmazenada.size() != tamanho) {
                throw new IllegalArgumentException("Página de cache inválida");
            }

            return Optional.of(paginaArmazenada);
        } catch (JsonProcessingException | IllegalArgumentException exception) {
            registrarFalha(exception);
            return Optional.empty();
        }
    }

    private void tentarArmazenarPagina(long tenantId, LeituraCache leitura, PaginaPedidos pagina) {
        if (invalidacoesPendentes.containsKey(tenantId)) {
            metricas.registrarGravacaoDescartada();
            return;
        }

        try {
            Long paginaArmazenada = redisTemplate.execute(
                    GRAVAR_PAGINA,
                    List.of(chaveVersao(tenantId), leitura.chavePagina()),
                    leitura.versao(),
                    objectMapper.writeValueAsString(pagina),
                    Long.toString(properties.ttl().toMillis()));

            if (!Long.valueOf(1).equals(paginaArmazenada)) {
                metricas.registrarGravacaoDescartada();
            }
        } catch (RuntimeException | JsonProcessingException exception) {
            registrarFalha(exception);
        }
    }

    private boolean repararInvalidacaoPendente(long tenantId) {
        Object marcadorInvalidacao = invalidacoesPendentes.get(tenantId);
        if (marcadorInvalidacao == null) {
            return true;
        }

        renovarVersao(tenantId);
        invalidacoesPendentes.remove(tenantId, marcadorInvalidacao);
        return !invalidacoesPendentes.containsKey(tenantId);
    }

    private void renovarVersao(long tenantId) {
        redisTemplate.opsForValue().set(chaveVersao(tenantId), UUID.randomUUID().toString());
        metricas.registrarInvalidacao();
    }

    private String chaveVersao(long tenantId) {
        return prefixoEmpresa(tenantId) + "generation";
    }

    private String chavePagina(long tenantId, String versao, int pagina, int tamanho) {
        return prefixoEmpresa(tenantId) + versao + ":page:" + pagina + ":size:" + tamanho;
    }

    private String prefixoEmpresa(long tenantId) {
        return properties.namespace() + ":tenant:{" + tenantId + "}:pedidos:";
    }

    private void registrarFalha(Exception exception) {
        metricas.registrarFalha();

        long agoraNanos = System.nanoTime();
        long proximoAviso = proximoAvisoNanos.get();
        if (agoraNanos >= proximoAviso
                && proximoAvisoNanos.compareAndSet(proximoAviso, agoraNanos + INTERVALO_ENTRE_AVISOS_NANOS)) {
            LOGGER.warn(
                    "Cache indisponível ou inválido ({}); operação seguirá pelo PostgreSQL.",
                    exception.getClass().getSimpleName());
        }
    }

    private static <T> DefaultRedisScript<T> carregarScript(String nome, Class<T> tipoResultado) {
        var script = new DefaultRedisScript<T>();
        script.setLocation(new ClassPathResource("cache/" + nome + ".lua"));
        script.setResultType(tipoResultado);
        return script;
    }

    private record LeituraCache(
            String versao,
            String chavePagina,
            Optional<PaginaPedidos> paginaArmazenada) {
    }
}
