package br.edu.tcc.pedidos;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.*;
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
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.*;
import org.testcontainers.images.builder.Transferable;
import org.testcontainers.utility.*;
import static br.edu.tcc.pedidos.Contratos.*;
import static org.assertj.core.api.Assertions.*;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CacheIntegrationTest {
    private static final String ADMIN_PASSWORD = "test-admin-password-0123456789abcdef0123456789";
    private static final String APP_PASSWORD = "test-cache-password-0123456789abcdef0123456789";
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(DockerImageName.parse(
            "postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"))
            .withInitScript("bootstrap.sql");
    @Container static final GenericContainer<?> REDIS = new GenericContainer<>(DockerImageName.parse(
            "redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85"))
            .withExposedPorts(6379)
            .withCopyFileToContainer(MountableFile.forHostPath("../infra/redis/redis.conf"), "/usr/local/etc/redis/redis.conf")
            .withCopyFileToContainer(MountableFile.forHostPath("../infra/redis/start-redis.sh"), "/usr/local/bin/start-redis.sh")
            .withCopyToContainer(Transferable.of(ADMIN_PASSWORD), "/run/secrets/redis_password")
            .withCopyToContainer(Transferable.of(APP_PASSWORD), "/run/secrets/redis_app_password")
            .withCreateContainerCmdModifier(cmd -> cmd.withEntrypoint("/bin/sh", "/usr/local/bin/start-redis.sh"));
    @DynamicPropertySource static void properties(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", () -> POSTGRES.getJdbcUrl() + "&currentSchema=tcc");
        r.add("spring.datasource.username", () -> "tcc_app");
        r.add("spring.datasource.password", () -> "application-test");
        r.add("DB_PASSWORD", () -> "application-test");
        r.add("spring.flyway.enabled", () -> true);
        r.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        r.add("spring.flyway.user", () -> "tcc_migrator");
        r.add("spring.flyway.password", () -> "migration-test");
        r.add("app.cache.enabled", () -> true);
        r.add("app.cache.host", REDIS::getHost);
        r.add("app.cache.port", () -> REDIS.getMappedPort(6379));
        r.add("app.cache.password", () -> APP_PASSWORD);
        r.add("app.cache.timeout", () -> "200ms");
    }
    @Autowired PedidoService pedidos;
    @Autowired ConsultaPedidosService consultas;
    @Autowired RedisPaginaCache cache;
    @Autowired StringRedisTemplate redis;
    @Autowired ObjectMapper mapper;
    @Autowired CacheProperties config;
    @Autowired PlatformTransactionManager transactions;
    @Autowired MeterRegistry meters;
    @LocalServerPort int port;
    private static LettuceConnectionFactory adminFactory;
    private static StringRedisTemplate admin;
    private long tenant, cliente;

    @BeforeAll static void adminConnection() {
        var server = new RedisStandaloneConfiguration(REDIS.getHost(), REDIS.getMappedPort(6379));
        server.setPassword(ADMIN_PASSWORD);
        adminFactory = new LettuceConnectionFactory(server);
        adminFactory.afterPropertiesSet();
        adminFactory.start();
        admin = new StringRedisTemplate(adminFactory);
    }
    @AfterAll static void cleanup() { if (adminFactory != null) adminFactory.destroy(); }
    @BeforeEach void data() {
        tenant = pedidos.criarEmpresa(new NovaEmpresa("Cache A")).id();
        cliente = pedidos.criarCliente(tenant, new NovoCliente("Cliente A")).id();
    }
    private PedidoResumo novo() { return pedidos.criarPedido(tenant, request(cliente)); }
    private NovoPedido request(long cliente) {
        return new NovoPedido(cliente, List.of(new NovoItem("Item", 2, new BigDecimal("12.35"))));
    }
    private String generationKey(long id) { return config.namespace() + ":tenant:{" + id + "}:pedidos:generation"; }
    private String generation(long id) { return admin.opsForValue().get(generationKey(id)); }
    private String pageKey(long id, String gen, int page, int size) {
        return config.namespace() + ":tenant:{" + id + "}:pedidos:" + gen + ":page:" + page + ":size:" + size;
    }
    private double counter(String name) { return meters.get(name).counter().count(); }

    @Test void hitPreservaContratoESemConsultarBanco() throws Exception {
        novo();
        var primeira = consultas.listar(tenant, 0, 20);
        var cached = cache.buscarOuCarregar(tenant, 0, 20, () -> { throw new AssertionError("Hit não deve ler PostgreSQL"); });
        assertThat(cached).isEqualTo(primeira);
        var response = HttpClient.newHttpClient().send(HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/pedidos?page=0&size=20"))
                .header("X-Tenant-Id", Long.toString(tenant)).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(mapper.readValue(response.body(), PaginaPedidos.class)).isEqualTo(primeira);
    }
    @Test void chavesSeparamEmpresasPaginasETamanhos() {
        var a = novo(); var b = novo();
        var tenantB = pedidos.criarEmpresa(new NovaEmpresa("Cache B")).id();
        var clienteB = pedidos.criarCliente(tenantB, new NovoCliente("Cliente B")).id();
        var outro = pedidos.criarPedido(tenantB, request(clienteB));
        assertThat(consultas.listar(tenant, 0, 1).content().getFirst().id()).isEqualTo(b.id());
        assertThat(consultas.listar(tenant, 1, 1).content().getFirst().id()).isEqualTo(a.id());
        assertThat(consultas.listar(tenant, 0, 2).content()).hasSize(2);
        assertThat(consultas.listar(tenantB, 0, 1).content().getFirst().id()).isEqualTo(outro.id());
        assertThat(consultas.listar(tenant, 0, 1).content().getFirst().id()).isEqualTo(b.id());
        assertThat(consultas.listar(tenant, 1, 1).content().getFirst().id()).isEqualTo(a.id());
    }
    @Test void criacaoEAtualizacaoInvalidamTodasAsPaginasSomenteDaEmpresa() {
        var a = novo(); novo();
        consultas.listar(tenant, 0, 1); consultas.listar(tenant, 1, 1); consultas.listar(tenant, 0, 20);
        var other = pedidos.criarEmpresa(new NovaEmpresa("Outra")).id();
        consultas.listar(other, 0, 20);
        var otherVersion = generation(other);
        var before = generation(tenant);
        novo();
        assertThat(generation(tenant)).isNotEqualTo(before);
        assertThat(generation(other)).isEqualTo(otherVersion);
        assertThat(consultas.listar(tenant, 0, 1).totalElements()).isEqualTo(3);
        assertThat(consultas.listar(tenant, 1, 1).totalElements()).isEqualTo(3);
        assertThat(consultas.listar(tenant, 0, 20).content()).hasSize(3);
        before = generation(tenant);
        pedidos.alterarStatus(tenant, a.id(), new AlterarStatus(Status.CONFIRMADO));
        assertThat(generation(tenant)).isNotEqualTo(before);
        assertThat(consultas.listar(tenant, 0, 20).content().stream().filter(p -> p.id() == a.id()).findFirst().orElseThrow().status())
                .isEqualTo(Status.CONFIRMADO);
    }
    @Test void rollbackNaoInvalidaCache() {
        consultas.listar(tenant, 0, 20);
        var before = generation(tenant);
        new TransactionTemplate(transactions).executeWithoutResult(tx -> { novo(); tx.setRollbackOnly(); });
        assertThat(generation(tenant)).isEqualTo(before);
        assertThat(consultas.listar(tenant, 0, 20).totalElements()).isZero();
        assertThat(pedidos.listar(tenant, 0, 20).totalElements()).isZero();
    }
    @Test void ttlExpiraPaginaSemRenovacaoEmHits() {
        var shortConfig = new CacheProperties(true, "tcc:expiry", Duration.ofMillis(300), config.timeout(),
                config.host(), config.port(), config.username(), config.password());
        var shortCache = new RedisPaginaCache(redis, mapper, shortConfig, new SimpleMeterRegistry());
        var loads = new AtomicInteger();
        java.util.function.Supplier<PaginaPedidos> load = () -> { loads.incrementAndGet(); return pedidos.listar(tenant, 0, 20); };
        shortCache.buscarOuCarregar(tenant, 0, 20, load);
        String base = "tcc:expiry:tenant:{" + tenant + "}:pedidos:";
        String key = base + admin.opsForValue().get(base + "generation") + ":page:0:size:20";
        assertThat(admin.getExpire(key, TimeUnit.MILLISECONDS)).isBetween(1L, 300L);
        shortCache.buscarOuCarregar(tenant, 0, 20, load);
        assertThat(loads).hasValue(1);
        await().atMost(Duration.ofSeconds(3)).until(() -> !Boolean.TRUE.equals(admin.hasKey(key)));
        shortCache.buscarOuCarregar(tenant, 0, 20, load);
        assertThat(loads).hasValue(2);
    }
    @Test void leituraConcorrenteNaoRepopulaVersaoInvalidada() throws Exception {
        var read = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        double discardedBefore = counter("tcc.cache.discarded_writes");
        try (var executor = Executors.newSingleThreadExecutor()) {
            var future = executor.submit(() -> cache.buscarOuCarregar(tenant, 0, 20, () -> {
                var snapshot = pedidos.listar(tenant, 0, 20);
                read.countDown();
                try { if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("Timeout"); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new AssertionError(e); }
                return snapshot;
            }));
            try {
                assertThat(read.await(5, TimeUnit.SECONDS)).isTrue();
                String old = generation(tenant);
                novo(); release.countDown();
                assertThat(future.get(5, TimeUnit.SECONDS).totalElements()).isZero();
                assertThat(admin.hasKey(pageKey(tenant, old, 0, 20))).isFalse();
                assertThat(consultas.listar(tenant, 0, 20).totalElements()).isEqualTo(1);
                assertThat(counter("tcc.cache.discarded_writes")).isGreaterThan(discardedBefore);
            } finally { release.countDown(); }
        }
    }
    @Test void perdaDaVersaoNaoRessuscitaPaginaAntiga() {
        novo(); consultas.listar(tenant, 0, 20);
        String before = generation(tenant);
        String key = pageKey(tenant, before, 0, 20);
        assertThat(admin.hasKey(key)).isTrue();
        admin.delete(generationKey(tenant));
        var loads = new AtomicInteger();
        cache.buscarOuCarregar(tenant, 0, 20, () -> { loads.incrementAndGet(); return pedidos.listar(tenant, 0, 20); });
        assertThat(generation(tenant)).isNotEqualTo(before);
        assertThat(loads).hasValue(1);
    }
    @Test void jsonCorrompidoERecarregado() throws Exception {
        novo(); consultas.listar(tenant, 0, 20);
        String key = pageKey(tenant, generation(tenant), 0, 20);
        admin.opsForValue().set(key, "json-invalido");
        double errors = counter("tcc.cache.errors");
        assertThat(consultas.listar(tenant, 0, 20).totalElements()).isEqualTo(1);
        assertThat(mapper.readTree(admin.opsForValue().get(key)).get("totalElements").asLong()).isEqualTo(1);
        assertThat(counter("tcc.cache.errors")).isGreaterThan(errors);
    }
    @Test void falhaRedisNaoDesfazCommitEReparaInvalidacaoAoRecuperar() throws Exception {
        consultas.listar(tenant, 0, 20);
        String old = generation(tenant);
        REDIS.getDockerClient().pauseContainerCmd(REDIS.getContainerId()).exec();
        try {
            novo(); // Commit deve ter sucesso mesmo se a invalidação falhar.
            assertThat(consultas.listar(tenant, 0, 20).totalElements()).isEqualTo(1);
            var health = HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(
                    "http://localhost:" + port + "/actuator/health")).GET().build(), HttpResponse.BodyHandlers.ofString());
            assertThat(health.statusCode()).isEqualTo(200);
        } finally { REDIS.getDockerClient().unpauseContainerCmd(REDIS.getContainerId()).exec(); }
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
            assertThat(consultas.listar(tenant, 0, 20).totalElements()).isEqualTo(1);
            assertThat(generation(tenant)).isNotEqualTo(old);
        });
        assertThat(cache.buscarOuCarregar(tenant, 0, 20, () -> { throw new AssertionError("Deve ser hit após recuperação"); }).totalElements()).isEqualTo(1);
    }
    @Test void aclImpedeAcessoForaDoPrefixoEComandosAdministrativos() {
        assertThatThrownBy(() -> redis.opsForValue().get("outro:tenant:1")).rootCause().hasMessageContaining("NOPERM");
        assertThatThrownBy(() -> redis.keys("*")).rootCause().hasMessageContaining("NOPERM");
        assertThat(consultas.listar(tenant, 0, 20).totalElements()).isZero();
    }
    @Test void empresaInexistenteNaoTem404Armazenado() {
        assertThatThrownBy(() -> consultas.listar(Long.MAX_VALUE, 0, 20))
                .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThat(admin.keys(config.namespace() + ":tenant:{" + Long.MAX_VALUE + "}:pedidos:*:page:*")).isEmpty();
    }
}
