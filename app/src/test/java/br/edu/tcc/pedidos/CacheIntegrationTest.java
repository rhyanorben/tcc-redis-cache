package br.edu.tcc.pedidos;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import br.edu.tcc.pedidos.Contratos.AlterarStatus;
import br.edu.tcc.pedidos.Contratos.NovaEmpresa;
import br.edu.tcc.pedidos.Contratos.NovoCliente;
import br.edu.tcc.pedidos.Contratos.NovoItem;
import br.edu.tcc.pedidos.Contratos.NovoPedido;
import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import br.edu.tcc.pedidos.Contratos.PedidoResumo;
import br.edu.tcc.pedidos.Contratos.Status;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
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
        var servidor = new RedisStandaloneConfiguration(REDIS.getHost(), REDIS.getMappedPort(6379));
        servidor.setPassword(ADMIN_PASSWORD);
        conexaoAdministrador = new LettuceConnectionFactory(servidor);
        conexaoAdministrador.afterPropertiesSet();
        conexaoAdministrador.start();
        redisAdministrador = new StringRedisTemplate(conexaoAdministrador);
    }

    @AfterAll
    static void fecharConexaoAdministradorRedis() {
        if (conexaoAdministrador != null) {
            conexaoAdministrador.destroy();
        }
    }

    @BeforeEach
    void criarEmpresaECliente() {
        empresaId = pedidos.criarEmpresa(new NovaEmpresa("Cache A")).id();
        clienteId = pedidos.criarCliente(empresaId, new NovoCliente("Cliente A")).id();
    }

    @Test
    void hitPreservaContratoESemConsultarBanco() throws Exception {
        criarPedido();
        var paginaOriginal = consultas.listar(empresaId, 0, 20);

        var paginaEmCache = cache.buscarOuCarregar(empresaId, 0, 20, () -> {
            throw new AssertionError("Hit não deve ler PostgreSQL");
        });
        var resposta = consultarApi("/api/pedidos?page=0&size=20", empresaId);

        assertThat(paginaEmCache).isEqualTo(paginaOriginal);
        assertThat(resposta.statusCode()).isEqualTo(200);
        assertThat(json.readValue(resposta.body(), PaginaPedidos.class)).isEqualTo(paginaOriginal);
    }

    @Test
    void chavesSeparamEmpresasPaginasETamanhos() {
        var primeiroPedido = criarPedido();
        var segundoPedido = criarPedido();
        long outraEmpresaId = pedidos.criarEmpresa(new NovaEmpresa("Cache B")).id();
        long outroClienteId = pedidos.criarCliente(outraEmpresaId, new NovoCliente("Cliente B")).id();
        var pedidoOutraEmpresa = pedidos.criarPedido(outraEmpresaId, novoPedidoPara(outroClienteId));

        assertThat(consultas.listar(empresaId, 0, 1).content().getFirst().id()).isEqualTo(segundoPedido.id());
        assertThat(consultas.listar(empresaId, 1, 1).content().getFirst().id()).isEqualTo(primeiroPedido.id());
        assertThat(consultas.listar(empresaId, 0, 2).content()).hasSize(2);
        assertThat(consultas.listar(outraEmpresaId, 0, 1).content().getFirst().id())
                .isEqualTo(pedidoOutraEmpresa.id());
        assertThat(consultas.listar(empresaId, 0, 1).content().getFirst().id()).isEqualTo(segundoPedido.id());
        assertThat(consultas.listar(empresaId, 1, 1).content().getFirst().id()).isEqualTo(primeiroPedido.id());
    }

    @Test
    void criacaoEAtualizacaoInvalidamTodasAsPaginasSomenteDaEmpresa() {
        var pedidoParaAtualizar = criarPedido();
        criarPedido();
        consultas.listar(empresaId, 0, 1);
        consultas.listar(empresaId, 1, 1);
        consultas.listar(empresaId, 0, 20);
        long outraEmpresaId = pedidos.criarEmpresa(new NovaEmpresa("Outra")).id();
        consultas.listar(outraEmpresaId, 0, 20);
        String geracaoOutraEmpresa = buscarGeracaoCache(outraEmpresaId);
        String geracaoAntesDaCriacao = buscarGeracaoCache(empresaId);

        criarPedido();

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaCriacao);
        assertThat(buscarGeracaoCache(outraEmpresaId)).isEqualTo(geracaoOutraEmpresa);
        assertThat(consultas.listar(empresaId, 0, 1).totalElements()).isEqualTo(3);
        assertThat(consultas.listar(empresaId, 1, 1).totalElements()).isEqualTo(3);
        assertThat(consultas.listar(empresaId, 0, 20).content()).hasSize(3);

        String geracaoAntesDaAtualizacao = buscarGeracaoCache(empresaId);
        pedidos.alterarStatus(empresaId, pedidoParaAtualizar.id(), new AlterarStatus(Status.CONFIRMADO));

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaAtualizacao);

        var pedidoAtualizado = consultas.listar(empresaId, 0, 20).content().stream()
                .filter(pedido -> pedido.id() == pedidoParaAtualizar.id())
                .findFirst()
                .orElseThrow();

        assertThat(pedidoAtualizado.status()).isEqualTo(Status.CONFIRMADO);
    }

    @Test
    void rollbackNaoInvalidaCache() {
        consultas.listar(empresaId, 0, 20);
        String geracaoAntesDoRollback = buscarGeracaoCache(empresaId);

        new TransactionTemplate(gerenciadorTransacoes).executeWithoutResult(transacao -> {
            criarPedido();
            transacao.setRollbackOnly();
        });

        assertThat(buscarGeracaoCache(empresaId)).isEqualTo(geracaoAntesDoRollback);
        assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isZero();
        assertThat(pedidos.listar(empresaId, 0, 20).totalElements()).isZero();
    }

    @Test
    void ttlExpiraPaginaSemRenovacaoEmHits() {
        var configuracaoTtlCurto = new CacheProperties(
                true, "tcc:expiry", Duration.ofMillis(300), configuracaoCache.timeout(),
                configuracaoCache.host(), configuracaoCache.port(),
                configuracaoCache.username(), configuracaoCache.password());
        var cacheTtlCurto = new RedisPaginaCache(redis, json, configuracaoTtlCurto, new SimpleMeterRegistry());
        var carregamentos = new AtomicInteger();
        Supplier<PaginaPedidos> carregarPagina = () -> {
            carregamentos.incrementAndGet();
            return pedidos.listar(empresaId, 0, 20);
        };

        cacheTtlCurto.buscarOuCarregar(empresaId, 0, 20, carregarPagina);
        String prefixo = "tcc:expiry:tenant:{" + empresaId + "}:pedidos:";
        String geracao = redisAdministrador.opsForValue().get(prefixo + "generation");
        String chavePagina = prefixo + geracao + ":page:0:size:20";

        assertThat(redisAdministrador.getExpire(chavePagina, TimeUnit.MILLISECONDS)).isBetween(1L, 300L);

        cacheTtlCurto.buscarOuCarregar(empresaId, 0, 20, carregarPagina);

        assertThat(carregamentos).hasValue(1);

        await().atMost(Duration.ofSeconds(3))
                .until(() -> !Boolean.TRUE.equals(redisAdministrador.hasKey(chavePagina)));
        cacheTtlCurto.buscarOuCarregar(empresaId, 0, 20, carregarPagina);

        assertThat(carregamentos).hasValue(2);
    }

    @Test
    void leituraConcorrenteNaoRepopulaVersaoInvalidada() throws Exception {
        var paginaConsultada = new CountDownLatch(1);
        var liberarPreenchimento = new CountDownLatch(1);
        double descartesAntesDaInvalidacao = contarMetrica("tcc.cache.discarded_writes");

        try (var executor = Executors.newSingleThreadExecutor()) {
            var leituraConcorrente = executor.submit(() -> cache.buscarOuCarregar(empresaId, 0, 20, () -> {
                var paginaAntesDaCriacao = pedidos.listar(empresaId, 0, 20);
                paginaConsultada.countDown();
                aguardarPreenchimento(liberarPreenchimento);
                return paginaAntesDaCriacao;
            }));

            try {
                assertThat(paginaConsultada.await(5, TimeUnit.SECONDS)).isTrue();
                String geracaoAnterior = buscarGeracaoCache(empresaId);

                criarPedido();
                liberarPreenchimento.countDown();

                assertThat(leituraConcorrente.get(5, TimeUnit.SECONDS).totalElements()).isZero();
                assertThat(redisAdministrador.hasKey(chavePagina(empresaId, geracaoAnterior, 0, 20))).isFalse();
                assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isEqualTo(1);
                assertThat(contarMetrica("tcc.cache.discarded_writes")).isGreaterThan(descartesAntesDaInvalidacao);
            } finally {
                liberarPreenchimento.countDown();
            }
        }
    }

    @Test
    void perdaDaVersaoNaoRessuscitaPaginaAntiga() {
        criarPedido();
        consultas.listar(empresaId, 0, 20);
        String geracaoAnterior = buscarGeracaoCache(empresaId);
        String chavePaginaAnterior = chavePagina(empresaId, geracaoAnterior, 0, 20);

        assertThat(redisAdministrador.hasKey(chavePaginaAnterior)).isTrue();

        redisAdministrador.delete(chaveGeracao(empresaId));
        var carregamentos = new AtomicInteger();
        cache.buscarOuCarregar(empresaId, 0, 20, () -> {
            carregamentos.incrementAndGet();
            return pedidos.listar(empresaId, 0, 20);
        });

        assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAnterior);
        assertThat(carregamentos).hasValue(1);
    }

    @Test
    void jsonCorrompidoERecarregado() throws Exception {
        criarPedido();
        consultas.listar(empresaId, 0, 20);
        String chave = chavePagina(empresaId, buscarGeracaoCache(empresaId), 0, 20);
        redisAdministrador.opsForValue().set(chave, "json-invalido");
        double errosAntesDaLeitura = contarMetrica("tcc.cache.errors");

        assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isEqualTo(1);
        assertThat(json.readTree(redisAdministrador.opsForValue().get(chave)).get("totalElements").asLong())
                .isEqualTo(1);
        assertThat(contarMetrica("tcc.cache.errors")).isGreaterThan(errosAntesDaLeitura);
    }

    @Test
    void falhaRedisNaoDesfazCommitEReparaInvalidacaoAoRecuperar() throws Exception {
        consultas.listar(empresaId, 0, 20);
        String geracaoAntesDaFalha = buscarGeracaoCache(empresaId);
        REDIS.getDockerClient().pauseContainerCmd(REDIS.getContainerId()).exec();

        try {
            criarPedido();

            assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isEqualTo(1);
            assertThat(consultarApi("/actuator/health", null).statusCode()).isEqualTo(200);
        } finally {
            REDIS.getDockerClient().unpauseContainerCmd(REDIS.getContainerId()).exec();
        }

        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isEqualTo(1);
            assertThat(buscarGeracaoCache(empresaId)).isNotEqualTo(geracaoAntesDaFalha);
        });

        var paginaRecuperada = cache.buscarOuCarregar(empresaId, 0, 20, () -> {
            throw new AssertionError("Deve ser hit após recuperação");
        });

        assertThat(paginaRecuperada.totalElements()).isEqualTo(1);
    }

    @Test
    void aclImpedeAcessoForaDoPrefixoEComandosAdministrativos() {
        assertThatThrownBy(() -> redis.opsForValue().get("outro:tenant:1"))
                .rootCause().hasMessageContaining("NOPERM");
        assertThatThrownBy(() -> redis.keys("*"))
                .rootCause().hasMessageContaining("NOPERM");
        assertThat(consultas.listar(empresaId, 0, 20).totalElements()).isZero();
    }

    @Test
    void empresaInexistenteNaoTem404Armazenado() {
        assertThatThrownBy(() -> consultas.listar(Long.MAX_VALUE, 0, 20))
                .isInstanceOf(ResponseStatusException.class);
        assertThat(redisAdministrador.keys(
                configuracaoCache.namespace() + ":tenant:{" + Long.MAX_VALUE + "}:pedidos:*:page:*"))
                .isEmpty();
    }

    private PedidoResumo criarPedido() {
        return pedidos.criarPedido(empresaId, novoPedidoPara(clienteId));
    }

    private NovoPedido novoPedidoPara(long clienteId) {
        return new NovoPedido(clienteId, List.of(new NovoItem("Item", 2, new BigDecimal("12.35"))));
    }

    private String chaveGeracao(long empresaId) {
        return configuracaoCache.namespace() + ":tenant:{" + empresaId + "}:pedidos:generation";
    }

    private String buscarGeracaoCache(long empresaId) {
        return redisAdministrador.opsForValue().get(chaveGeracao(empresaId));
    }

    private String chavePagina(long empresaId, String geracao, int pagina, int tamanho) {
        return configuracaoCache.namespace() + ":tenant:{" + empresaId + "}:pedidos:"
                + geracao + ":page:" + pagina + ":size:" + tamanho;
    }

    private double contarMetrica(String nome) {
        return metricas.get(nome).counter().count();
    }

    private HttpResponse<String> consultarApi(String caminho, Long empresaId) throws Exception {
        var requisicao = HttpRequest.newBuilder(URI.create("http://localhost:" + porta + caminho)).GET();
        if (empresaId != null) {
            requisicao.header("X-Tenant-Id", empresaId.toString());
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
