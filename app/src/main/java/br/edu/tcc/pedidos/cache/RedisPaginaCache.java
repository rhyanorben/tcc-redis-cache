package br.edu.tcc.pedidos.cache;

import br.edu.tcc.pedidos.config.CacheProperties;
import br.edu.tcc.pedidos.model.PedidoResumo;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;
import org.apache.commons.lang3.ObjectUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
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
    public Page<PedidoResumo> buscarOuCarregar(
            long tenantId,
            Pageable pageable,
            Supplier<Page<PedidoResumo>> carregarDoBanco) {
        Optional<LeituraCache> leituraCache = tentarLerPagina(tenantId, pageable);

        if (leituraCache.isEmpty()) {
            metricas.registrarConsultaAoBancoPorFalha();
            return carregarDoBanco.get();
        }

        LeituraCache leitura = leituraCache.get();
        if (leitura.paginaArmazenada().isPresent()) {
            metricas.registrarAcerto();
            return leitura.paginaArmazenada().get();
        }

        metricas.registrarAusencia();
        Page<PedidoResumo> paginaConsultada = carregarDoBanco.get();
        tentarArmazenarPagina(tenantId, leitura, paginaConsultada);
        return paginaConsultada;
    }

    @Override
    public void invalidar(long tenantId) {
        Object marcadorInvalidacao = new Object();
        invalidacoesPendentes.put(tenantId, marcadorInvalidacao);

        try {
            renovarVersao(tenantId);
            invalidacoesPendentes.remove(tenantId, marcadorInvalidacao);
        } catch (RuntimeException exception) {
            registrarFalha(exception);
        }
    }

    private Optional<LeituraCache> tentarLerPagina(long tenantId, Pageable pageable) {
        try {
            if (!repararInvalidacaoPendente(tenantId)) {
                return Optional.empty();
            }

            String versao = obterOuCriarVersao(tenantId);
            String chavePagina = chavePagina(tenantId, versao, pageable);
            String jsonPagina = redisTemplate.execute(
                    LER_PAGINA,
                    List.of(chaveVersao(tenantId), chavePagina),
                    versao);
            Optional<Page<PedidoResumo>> paginaArmazenada = deserializarPagina(jsonPagina, pageable);

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

        if (ObjectUtils.isEmpty(versao)) {
            throw new IllegalStateException("Redis não retornou a versão do cache");
        }

        return versao;
    }

    private Optional<Page<PedidoResumo>> deserializarPagina(String jsonPagina, Pageable pageable) {
        if (ObjectUtils.isEmpty(jsonPagina)) {
            return Optional.empty();
        }

        try {
            PaginaPedidosCache paginaArmazenada = objectMapper.readValue(jsonPagina, PaginaPedidosCache.class);
            if (ObjectUtils.isEmpty(paginaArmazenada)
                    || paginaArmazenada.totalElements() < 0
                    || paginaArmazenada.content().size() > pageable.getPageSize()) {
                throw new IllegalArgumentException("Página de cache inválida");
            }

            return Optional.of(new PageImpl<>(paginaArmazenada.content(), pageable, paginaArmazenada.totalElements()));
        } catch (JsonProcessingException | IllegalArgumentException exception) {
            registrarFalha(exception);
            return Optional.empty();
        }
    }

    private void tentarArmazenarPagina(long tenantId, LeituraCache leitura, Page<PedidoResumo> pagina) {
        if (invalidacoesPendentes.containsKey(tenantId)) {
            metricas.registrarGravacaoDescartada();
            return;
        }

        try {
            PaginaPedidosCache snapshot = new PaginaPedidosCache(pagina.getContent(), pagina.getTotalElements());
            Long paginaArmazenada = redisTemplate.execute(
                    GRAVAR_PAGINA,
                    List.of(chaveVersao(tenantId), leitura.chavePagina()),
                    leitura.versao(),
                    objectMapper.writeValueAsString(snapshot),
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
        if (ObjectUtils.isEmpty(marcadorInvalidacao)) {
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

    private String chavePagina(long tenantId, String versao, Pageable pageable) {
        return prefixoEmpresa(tenantId) + versao
                + ":page:" + pageable.getPageNumber()
                + ":size:" + pageable.getPageSize()
                + ":sort:" + hashOrdenacao(pageable);
    }

    private String hashOrdenacao(Pageable pageable) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] ordenacao = pageable.getSort().toString().getBytes(StandardCharsets.UTF_8);
            return HexFormat.of().formatHex(digest.digest(ordenacao));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 indisponível", exception);
        }
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
        DefaultRedisScript<T> script = new DefaultRedisScript<>();
        script.setLocation(new ClassPathResource("cache/" + nome + ".lua"));
        script.setResultType(tipoResultado);
        return script;
    }
}
