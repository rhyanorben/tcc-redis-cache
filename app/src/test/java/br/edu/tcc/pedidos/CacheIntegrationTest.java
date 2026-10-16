package br.edu.tcc.pedidos;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import br.edu.tcc.pedidos.cache.RedisPaginaCache;
import br.edu.tcc.pedidos.config.CacheProperties;
import br.edu.tcc.pedidos.model.ItemPedido;
import br.edu.tcc.pedidos.model.Pedido;
import br.edu.tcc.pedidos.model.PedidoResumo;
import br.edu.tcc.pedidos.model.StatusPedido;
import br.edu.tcc.pedidos.service.ClienteService;
import br.edu.tcc.pedidos.service.ConsultaPedidosService;
import br.edu.tcc.pedidos.service.EmpresaService;
import br.edu.tcc.pedidos.service.PedidoService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.apache.commons.lang3.ObjectUtils;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.images.builder.Transferable;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CacheIntegrationTest {

    private static final String ADMIN_PASSWORD = "test-admin-password-0123456789abcdef0123456789";
    private static final String APP_PASSWORD = "test-cache-password-0123456789abcdef0123456789";

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(DockerImageName.parse(
            "postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"))
            .withInitScript("bootstrap.sql");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>(DockerImageName.parse(
            "redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85"))
            .withExposedPorts(6379)
            .withCopyFileToContainer(
                    MountableFile.forHostPath("../infra/redis/redis.conf"), "/usr/local/etc/redis/redis.conf")
            .withCopyFileToContainer(
                    MountableFile.forHostPath("../infra/redis/start-redis.sh"), "/usr/local/bin/start-redis.sh")
            .withCopyToContainer(Transferable.of(ADMIN_PASSWORD), "/run/secrets/redis_password")
            .withCopyToContainer(Transferable.of(APP_PASSWORD), "/run/secrets/redis_app_password")
            .withCreateContainerCmdModifier(
                    comando -> comando.withEntrypoint("/bin/sh", "/usr/local/bin/start-redis.sh"));

    private static LettuceConnectionFactory conexaoAdministrador;
    private static StringRedisTemplate redisAdministrador;

    @Autowired
    EmpresaService empresas;

    @Autowired
    ClienteService clientes;

    @Autowired
    PedidoService pedidos;

    @Autowired
    ConsultaPedidosService consultas;

    @Autowired
    RedisPaginaCache cache;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    ObjectMapper json;

    @Autowired
    CacheProperties configuracaoCache;

    @Autowired
    PlatformTransactionManager gerenciadorTransacoes;

    @Autowired
    MeterRegistry metricas;

    @LocalServerPort
    int porta;

    private final HttpClient clienteHttp = HttpClient.newHttpClient();
    private long empresaId;
    private long clienteId;

    @DynamicPropertySource
    static void configurarAplicacao(DynamicPropertyRegistry propriedades) {
        propriedades.add("spring.datasource.url", () -> POSTGRES.getJdbcUrl() + "&currentSchema=tcc");
        propriedades.add("spring.datasource.username", () -> "tcc_app");
        propriedades.add("spring.datasource.password", () -> "application-test");
        propriedades.add("DB_PASSWORD", () -> "application-test");
        propriedades.add("spring.flyway.enabled", () -> true);
        propriedades.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        propriedades.add("spring.flyway.user", () -> "tcc_migrator");
        propriedades.add("spring.flyway.password", () -> "migration-test");
        propriedades.add("app.cache.enabled", () -> true);
        propriedades.add("app.cache.host", REDIS::getHost);
        propriedades.add("app.cache.port", () -> REDIS.getMappedPort(6379));
        propriedades.add("app.cache.password", () -> APP_PASSWORD);
        propriedades.add("app.cache.timeout", () -> "200ms");
    }

    @BeforeAll
    static void conectarAdministradorRedis() {
        RedisStandaloneConfiguration servidor = new RedisStandaloneConfiguration(
                REDIS.getHost(), REDIS.getMappedPort(6379));
        servidor.setPassword(ADMIN_PASSWORD);
        conexaoAdministrador = new LettuceConnectionFactory(servidor);
        conexaoAdministrador.afterPropertiesSet();
        conexaoAdministrador.start();
        redisAdministrador = new StringRedisTemplate(conexaoAdministrador);
    }

    @AfterAll
    static void fecharConexaoAdministradorRedis() {
        if (ObjectUtils.isNotEmpty(conexaoAdministrador)) {
            conexaoAdministrador.destroy();
        }
    }

    @BeforeEach
    void criarEmpresaECliente() {
        empresaId = empresas.criarEmpresa("Cache A").getId();
        clienteId = clientes.criarCliente(empresaId, "Cliente A").getId();
    }

    @Test
    void hitPreservaContratoESemConsultarBanco() throws Exception {
        criarPedido();
        Page<PedidoResumo> paginaOriginal = consultas.listar(empresaId, paginacao(0, 20));

        Page<PedidoResumo> paginaEmCache = cache.buscarOuCarregar(empresaId, paginacao(0, 20), () -> {
            throw new AssertionError("Hit não deve ler PostgreSQL");
        });
        HttpResponse<String> resposta = consultarApi("/api/pedidos?page=0&size=20", empresaId);

        assertThat(paginaEmCache).isEqualTo(paginaOriginal);
        assertThat(resposta.statusCode()).isEqualTo(200);
        JsonNode respostaJson = json.readTree(resposta.body());
        assertThat(respostaJson.get("content")).isEqualTo(json.readTree(json.writeValueAsString(paginaOriginal.getContent())));
        assertThat(respostaJson.get("totalElements").asLong()).isEqualTo(paginaOriginal.getTotalElements());
        assertThat(respostaJson.get("page").asInt()).isEqualTo(paginaOriginal.getNumber());
        assertThat(respostaJson.get("size").asInt()).isEqualTo(paginaOriginal.getSize());
    }

    @Test
    void chavesSeparamEmpresasPaginasETamanhos() {
        Pedido primeiroPedido = criarPedido();
        Pedido segundoPedido = criarPedido();
        long outraEmpresaId = empresas.criarEmpresa("Cache B").getId();
        long outroClienteId = clientes.criarCliente(outraEmpresaId, "Cliente B").getId();
        Pedido pedidoOutraEmpresa = pedidos.criarPedido(outraEmpresaId, outroClienteId, itensPedido());

        assertThat(consultas.listar(empresaId, paginacao(0, 1)).getContent().getFirst().id())
                .isEqualTo(segundoPedido.getId());
        assertThat(consultas.listar(empresaId, paginacao(1, 1)).getContent().getFirst().id())
                .isEqualTo(primeiroPedido.getId());
        assertThat(consultas.listar(empresaId, paginacao(0, 2)).getContent()).hasSize(2);
        assertThat(consultas.listar(outraEmpresaId, paginacao(0, 1)).getContent().getFirst().id())
                .isEqualTo(pedidoOutraEmpresa.getId());
        assertThat(consultas.listar(empresaId, paginacao(0, 1)).getContent().getFirst().id())
                .isEqualTo(segundoPedido.getId());
        assertThat(consultas.listar(empresaId, paginacao(1, 1)).getContent().getFirst().id())
                .isEqualTo(primeiroPedido.getId());
    }

    @Test
    void criacaoEAtualizacaoInvalidamTodasAsPaginasSomenteDaEmpresa() {
        Pedido pedidoParaAtualizar = criarPedido();
        criarPedido();
        consultas.listar(empresaId, paginacao(0, 1));
        consultas.listar(empresaId, paginacao(1, 1));
        consultas.listar(empresaId, paginacao(0, 20));
        long outraEmpresaId = empresas.criarEmpresa("Outra").getId();
        consultas.listar(outraEmpresaId, paginacao(0, 20));
        String geracaoOutraEmpresa = buscarGeracaoCache(outraEmpresaId);
        String geracaoAntesDaCriacao = buscarGeracaoCache(empresaId);

        criarPedido();

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaCriacao);
        assertThat(buscarGeracaoCache(outraEmpresaId)).isEqualTo(geracaoOutraEmpresa);
        assertThat(consultas.listar(empresaId, paginacao(0, 1)).getTotalElements()).isEqualTo(3);
        assertThat(consultas.listar(empresaId, paginacao(1, 1)).getTotalElements()).isEqualTo(3);
        assertThat(consultas.listar(empresaId, paginacao(0, 20)).getContent()).hasSize(3);

        String geracaoAntesDaAtualizacao = buscarGeracaoCache(empresaId);
        pedidos.alterarStatus(empresaId, pedidoParaAtualizar.getId(), StatusPedido.CONFIRMADO);

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaAtualizacao);

        PedidoResumo pedidoAtualizado = consultas.listar(empresaId, paginacao(0, 20)).getContent().stream()
                .filter(pedido -> pedido.id() == pedidoParaAtualizar.getId())
                .findFirst()
                .orElseThrow();

        assertThat(pedidoAtualizado.status()).isEqualTo(StatusPedido.CONFIRMADO);
    }

    @Test
    void rollbackNaoInvalidaCache() {
        consultas.listar(empresaId, paginacao(0, 20));
        String geracaoAntesDoRollback = buscarGeracaoCache(empresaId);

        new TransactionTemplate(gerenciadorTransacoes).executeWithoutResult(transacao -> {
            criarPedido();
            transacao.setRollbackOnly();
        });

        assertThat(buscarGeracaoCache(empresaId)).isEqualTo(geracaoAntesDoRollback);
        assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isZero();
        assertThat(pedidos.listar(empresaId, paginacao(0, 20)).getTotalElements()).isZero();
    }

    @Test
    void ttlExpiraPaginaSemRenovacaoEmHits() {
        CacheProperties configuracaoTtlCurto = new CacheProperties(
                true, "tcc:expiry", Duration.ofMillis(300), configuracaoCache.timeout(),
                configuracaoCache.host(), configuracaoCache.port(),
                configuracaoCache.username(), configuracaoCache.password());
        RedisPaginaCache cacheTtlCurto = new RedisPaginaCache(redis, json, configuracaoTtlCurto, new SimpleMeterRegistry());
        AtomicInteger carregamentos = new AtomicInteger();
        Supplier<Page<PedidoResumo>> carregarPagina = () -> {
            carregamentos.incrementAndGet();
            return pedidos.listar(empresaId, paginacao(0, 20));
        };

        cacheTtlCurto.buscarOuCarregar(empresaId, paginacao(0, 20), carregarPagina);
        String prefixo = "tcc:expiry:tenant:{" + empresaId + "}:pedidos:";
        String geracao = redisAdministrador.opsForValue().get(prefixo + "generation");
        String chavePagina = prefixo + geracao + ":page:0:size:20:sort:"
                + assinaturaOrdenacao(paginacao(0, 20));

        assertThat(redisAdministrador.getExpire(chavePagina, TimeUnit.MILLISECONDS)).isBetween(1L, 300L);

        cacheTtlCurto.buscarOuCarregar(empresaId, paginacao(0, 20), carregarPagina);

        assertThat(carregamentos).hasValue(1);

        await().atMost(Duration.ofSeconds(3))
                .until(() -> !Boolean.TRUE.equals(redisAdministrador.hasKey(chavePagina)));
        cacheTtlCurto.buscarOuCarregar(empresaId, paginacao(0, 20), carregarPagina);

        assertThat(carregamentos).hasValue(2);
    }

    @Test
    void leituraConcorrenteNaoRepopulaVersaoInvalidada() throws Exception {
        CountDownLatch paginaConsultada = new CountDownLatch(1);
        CountDownLatch liberarPreenchimento = new CountDownLatch(1);
        double descartesAntesDaInvalidacao = contarMetrica("tcc.cache.discarded_writes");

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<Page<PedidoResumo>> leituraConcorrente = executor.submit(() -> cache.buscarOuCarregar(
                    empresaId, paginacao(0, 20), () -> {
                        Page<PedidoResumo> paginaAntesDaCriacao = pedidos.listar(empresaId, paginacao(0, 20));
                        paginaConsultada.countDown();
                        aguardarPreenchimento(liberarPreenchimento);
                        return paginaAntesDaCriacao;
                    }));

            try {
                assertThat(paginaConsultada.await(5, TimeUnit.SECONDS)).isTrue();
                String geracaoAnterior = buscarGeracaoCache(empresaId);

                criarPedido();
                liberarPreenchimento.countDown();

                assertThat(leituraConcorrente.get(5, TimeUnit.SECONDS).getTotalElements()).isZero();
                assertThat(redisAdministrador.hasKey(chavePagina(empresaId, geracaoAnterior, 0, 20))).isFalse();
                assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isEqualTo(1);
                assertThat(contarMetrica("tcc.cache.discarded_writes")).isGreaterThan(descartesAntesDaInvalidacao);
            } finally {
                liberarPreenchimento.countDown();
            }
        }
    }

    @Test
    void perdaDaVersaoNaoRessuscitaPaginaAntiga() {
        criarPedido();
        consultas.listar(empresaId, paginacao(0, 20));
        String geracaoAnterior = buscarGeracaoCache(empresaId);
        String chavePaginaAnterior = chavePagina(empresaId, geracaoAnterior, 0, 20);

        assertThat(redisAdministrador.hasKey(chavePaginaAnterior)).isTrue();

        redisAdministrador.delete(chaveGeracao(empresaId));
        AtomicInteger carregamentos = new AtomicInteger();
        cache.buscarOuCarregar(empresaId, paginacao(0, 20), () -> {
            carregamentos.incrementAndGet();
            return pedidos.listar(empresaId, paginacao(0, 20));
        });

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAnterior);
        assertThat(carregamentos).hasValue(1);
    }

    @Test
    void jsonCorrompidoERecarregado() throws Exception {
        criarPedido();
        consultas.listar(empresaId, paginacao(0, 20));
        String chave = chavePagina(empresaId, buscarGeracaoCache(empresaId), 0, 20);
        redisAdministrador.opsForValue().set(chave, "json-invalido");
        double errosAntesDaLeitura = contarMetrica("tcc.cache.errors");

        assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isEqualTo(1);
        assertThat(json.readTree(redisAdministrador.opsForValue().get(chave)).get("totalElements").asLong())
                .isEqualTo(1);
        assertThat(contarMetrica("tcc.cache.errors")).isGreaterThan(errosAntesDaLeitura);
    }

    @Test
    void falhaRedisNaoDesfazCommitEReparaInvalidacaoAoRecuperar() throws Exception {
        consultas.listar(empresaId, paginacao(0, 20));
        String geracaoAntesDaFalha = buscarGeracaoCache(empresaId);
        REDIS.getDockerClient().pauseContainerCmd(REDIS.getContainerId()).exec();

        try {
            criarPedido();

            assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isEqualTo(1);
            assertThat(consultarApi("/actuator/health", null).statusCode()).isEqualTo(200);
        } finally {
            REDIS.getDockerClient().unpauseContainerCmd(REDIS.getContainerId()).exec();
        }

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isEqualTo(1);
            assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaFalha);
        });

        Page<PedidoResumo> paginaRecuperada = cache.buscarOuCarregar(empresaId, paginacao(0, 20), () -> {
            throw new AssertionError("Deve ser hit após recuperação");
        });

        assertThat(paginaRecuperada.getTotalElements()).isEqualTo(1);
    }

    @Test
    void aclImpedeAcessoForaDoPrefixoEComandosAdministrativos() {
        assertThatThrownBy(() -> redis.opsForValue().get("outro:tenant:1"))
                .rootCause().hasMessageContaining("NOPERM");
        assertThatThrownBy(() -> redis.keys("*"))
                .rootCause().hasMessageContaining("NOPERM");
        assertThat(consultas.listar(empresaId, paginacao(0, 20)).getTotalElements()).isZero();
    }

    @Test
    void empresaInexistenteNaoTem404Armazenado() {
        assertThatThrownBy(() -> consultas.listar(Long.MAX_VALUE, paginacao(0, 20)))
                .isInstanceOf(ResponseStatusException.class);
        assertThat(redisAdministrador.keys(
                configuracaoCache.namespace() + ":tenant:{" + Long.MAX_VALUE + "}:pedidos:*:page:*"))
                .isEmpty();
    }

    @Test
    void ordenacoesOpostasUsamPaginasDeCacheIndependentes() {
        Pedido primeiroPedido = criarPedido();
        Pedido segundoPedido = criarPedido();
        Pageable crescente = PageRequest.of(0, 1, Sort.by(Sort.Direction.ASC, "id"));
        Pageable decrescente = PageRequest.of(0, 1, Sort.by(Sort.Direction.DESC, "id"));

        Page<PedidoResumo> paginaCrescente = consultas.listar(empresaId, crescente);
        Page<PedidoResumo> paginaDecrescente = consultas.listar(empresaId, decrescente);
        Page<PedidoResumo> crescenteEmCache = cache.buscarOuCarregar(empresaId, crescente, () -> {
            throw new AssertionError("A ordenação crescente deve estar no cache");
        });
        Page<PedidoResumo> decrescenteEmCache = cache.buscarOuCarregar(empresaId, decrescente, () -> {
            throw new AssertionError("A ordenação decrescente deve estar no cache");
        });

        assertThat(paginaCrescente.getContent().getFirst().id()).isEqualTo(primeiroPedido.getId());
        assertThat(paginaDecrescente.getContent().getFirst().id()).isEqualTo(segundoPedido.getId());
        assertThat(crescenteEmCache).isEqualTo(paginaCrescente);
        assertThat(decrescenteEmCache).isEqualTo(paginaDecrescente);
        assertThat(crescenteEmCache.getSort()).isEqualTo(crescente.getSort());
        assertThat(decrescenteEmCache.getSort()).isEqualTo(decrescente.getSort());
    }

    @Test
    void paginaAlemDoTotalPreservaMetadadosNoCache() {
        criarPedido();
        criarPedido();
        Pageable foraDoIntervalo = paginacao(5, 1);
        Page<PedidoResumo> paginaOriginal = consultas.listar(empresaId, foraDoIntervalo);

        Page<PedidoResumo> paginaEmCache = cache.buscarOuCarregar(empresaId, foraDoIntervalo, () -> {
            throw new AssertionError("Uma página sem conteúdo também deve ser armazenada");
        });

        assertThat(paginaEmCache).isEqualTo(paginaOriginal);
        assertThat(paginaEmCache.getContent()).isEmpty();
        assertThat(paginaEmCache.getTotalElements()).isEqualTo(2);
        assertThat(paginaEmCache.getTotalPages()).isEqualTo(2);
        assertThat(paginaEmCache.getNumber()).isEqualTo(5);
        assertThat(paginaEmCache.isFirst()).isFalse();
        assertThat(paginaEmCache.isLast()).isTrue();
    }

    private Pedido criarPedido() {
        return pedidos.criarPedido(empresaId, clienteId, itensPedido());
    }

    private List<ItemPedido> itensPedido() {
        return List.of(new ItemPedido("Item", 2, new BigDecimal("12.35")));
    }

    private Pageable paginacao(int pagina, int tamanho) {
        Sort ordenacao = Sort.by(Sort.Order.desc("criadoEm"), Sort.Order.desc("id"));
        return PageRequest.of(pagina, tamanho, ordenacao);
    }

    private String chaveGeracao(long empresaId) {
        return configuracaoCache.namespace() + ":tenant:{" + empresaId + "}:pedidos:generation";
    }

    private String buscarGeracaoCache(long empresaId) {
        return redisAdministrador.opsForValue().get(chaveGeracao(empresaId));
    }

    private String chavePagina(long empresaId, String geracao, int pagina, int tamanho) {
        return configuracaoCache.namespace() + ":tenant:{" + empresaId + "}:pedidos:"
                + geracao + ":page:" + pagina + ":size:" + tamanho
                + ":sort:" + assinaturaOrdenacao(paginacao(pagina, tamanho));
    }

    private String assinaturaOrdenacao(Pageable paginacao) {
        try {
            MessageDigest algoritmo = MessageDigest.getInstance("SHA-256");
            byte[] assinatura = algoritmo.digest(paginacao.getSort().toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(assinatura);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private double contarMetrica(String nome) {
        return metricas.get(nome).counter().count();
    }

    private HttpResponse<String> consultarApi(String caminho, Long empresaId) throws Exception {
        HttpRequest.Builder requisicao = HttpRequest.newBuilder(URI.create("http://localhost:" + porta + caminho)).GET();
        if (ObjectUtils.isNotEmpty(empresaId)) {
            requisicao.header("tenantId", empresaId.toString());
        }
        return clienteHttp.send(requisicao.build(), HttpResponse.BodyHandlers.ofString());
    }

    private void aguardarPreenchimento(CountDownLatch liberarPreenchimento) {
        try {
            if (!liberarPreenchimento.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Tempo excedido ao aguardar o preenchimento do cache");
            }
        } catch (InterruptedException interrupcao) {
            Thread.currentThread().interrupt();
            throw new AssertionError(interrupcao);
        }
    }
}
