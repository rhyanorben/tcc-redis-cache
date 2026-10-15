package br.edu.tcc.pedidos;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.sql.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import static org.assertj.core.api.Assertions.*;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PedidosIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(
            DockerImageName.parse("postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"))
            .withInitScript("bootstrap.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> POSTGRES.getJdbcUrl() + "&currentSchema=tcc");
        registry.add("spring.datasource.username", () -> "tcc_app");
        registry.add("spring.datasource.password", () -> "application-test");
        registry.add("DB_PASSWORD", () -> "application-test");
        registry.add("spring.flyway.enabled", () -> true);
        registry.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        registry.add("spring.flyway.user", () -> "tcc_migrator");
        registry.add("spring.flyway.password", () -> "migration-test");
    }

    @LocalServerPort int port;
    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();
    private long empresaA, empresaB, clienteA, clienteB;

    @BeforeEach
    void prepare() throws Exception {
        empresaA = body(call("POST", "/api/empresas", null, "{\"nome\":\"Empresa A\"}", 201)).get("id").asLong();
        empresaB = body(call("POST", "/api/empresas", null, "{\"nome\":\"Empresa B\"}", 201)).get("id").asLong();
        clienteA = body(call("POST", "/api/clientes", empresaA, "{\"nome\":\"Cliente A\"}", 201)).get("id").asLong();
        clienteB = body(call("POST", "/api/clientes", empresaB, "{\"nome\":\"Cliente B\"}", 201)).get("id").asLong();
    }
    private String payload(long cliente) {
        return "{\"clienteId\":" + cliente + ",\"itens\":[{\"descricao\":\"Item\",\"quantidade\":2,\"precoUnitario\":12.35}]}";
    }
    private JsonNode pedido(long tenant, long cliente) throws Exception {
        return body(call("POST", "/api/pedidos", tenant, payload(cliente), 201));
    }
    private HttpResponse<String> call(String method, String path, Long tenant, String data, int expected) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
                .header("Content-Type", "application/json")
                .method(method, data == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(data));
        if (tenant != null) builder.header("X-Tenant-Id", tenant.toString());
        var response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).as(response.body()).isEqualTo(expected);
        return response;
    }
    private JsonNode body(HttpResponse<String> response) throws Exception { return json.readTree(response.body()); }
    private Connection admin() throws SQLException {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }

    @Test void paginacaoIsolaEmpresaEContagem() throws Exception {
        var first = pedido(empresaA, clienteA);
        var second = pedido(empresaA, clienteA);
        pedido(empresaB, clienteB);
        var page0 = body(call("GET", "/api/pedidos?page=0&size=1", empresaA, null, 200));
        var page1 = body(call("GET", "/api/pedidos?page=1&size=1", empresaA, null, 200));
        assertThat(page0.get("totalElements").asLong()).isEqualTo(2);
        assertThat(page0.get("totalPages").asLong()).isEqualTo(2);
        assertThat(page0.get("content").get(0).get("id").asLong()).isEqualTo(second.get("id").asLong());
        assertThat(page1.get("content").get(0).get("id").asLong()).isEqualTo(first.get("id").asLong());
        assertThat(page1.get("last").asBoolean()).isTrue();
        assertThat(page0.get("content").get(0).get("total").decimalValue()).isEqualByComparingTo(new BigDecimal("24.70"));
    }
    @Test void desempataPedidosComMesmoHorarioPorId() throws Exception {
        var a = pedido(empresaA, clienteA);
        var b = pedido(empresaA, clienteA);
        try (var c = admin(); var s = c.prepareStatement("UPDATE tcc.pedido SET criado_em = '2026-01-01T00:00:00Z' WHERE tenant_id = ?")) {
            s.setLong(1, empresaA); s.executeUpdate();
        }
        var p = body(call("GET", "/api/pedidos?size=2", empresaA, null, 200));
        assertThat(p.get("content").get(0).get("id").asLong()).isEqualTo(b.get("id").asLong());
        assertThat(p.get("content").get(1).get("id").asLong()).isEqualTo(a.get("id").asLong());
    }
    @Test void rejeitaClienteDeOutraEmpresaSemCriarPedidoOuItens() throws Exception {
        call("POST", "/api/pedidos", empresaA, payload(clienteB), 404);
        var p = body(call("GET", "/api/pedidos", empresaA, null, 200));
        assertThat(p.get("totalElements").asLong()).isZero();
        try (var c = admin(); var s = c.prepareStatement("SELECT count(*) FROM tcc.item_pedido WHERE tenant_id = ?")) {
            s.setLong(1, empresaA);
            try (var rows = s.executeQuery()) { rows.next(); assertThat(rows.getLong(1)).isZero(); }
        }
    }
    @Test void atualizacaoNaoAtravessaEmpresas() throws Exception {
        long id = pedido(empresaA, clienteA).get("id").asLong();
        call("PATCH", "/api/pedidos/" + id + "/status", empresaB, "{\"status\":\"CANCELADO\"}", 404);
        var p = body(call("GET", "/api/pedidos", empresaA, null, 200));
        assertThat(p.get("content").get(0).get("status").asText()).isEqualTo("ABERTO");
        var updated = body(call("PATCH", "/api/pedidos/" + id + "/status", empresaA, "{\"status\":\"CONFIRMADO\"}", 200));
        assertThat(updated.get("status").asText()).isEqualTo("CONFIRMADO");
    }
    @Test void exigeTenantEValidaLimites() throws Exception {
        call("GET", "/api/pedidos", null, null, 400);
        call("GET", "/api/pedidos", 0L, null, 400);
        for (var query : List.of("page=-1", "size=0", "size=101", "page=1000001", "page=abc"))
            call("GET", "/api/pedidos?" + query, empresaA, null, 400);
        call("GET", "/api/pedidos", Long.MAX_VALUE, null, 404);
    }
    @Test void paginasVaziasTemMetadadosConsistentes() throws Exception {
        var empty = body(call("GET", "/api/pedidos", empresaA, null, 200));
        assertThat(empty.get("totalElements").asLong()).isZero();
        assertThat(empty.get("totalPages").asLong()).isZero();
        assertThat(empty.get("first").asBoolean()).isTrue();
        assertThat(empty.get("last").asBoolean()).isTrue();
        pedido(empresaA, clienteA);
        var beyond = body(call("GET", "/api/pedidos?page=10&size=1", empresaA, null, 200));
        assertThat(beyond.get("content").size()).isZero();
        assertThat(beyond.get("totalElements").asLong()).isEqualTo(1);
    }
    @Test void validaItensEPrecisaoMonetaria() throws Exception {
        for (var itens : List.of("[]", "[null]", "[{\"descricao\":\"A\",\"quantidade\":0,\"precoUnitario\":1}]",
                "[{\"descricao\":\"A\",\"quantidade\":1,\"precoUnitario\":1.001}]")) {
            call("POST", "/api/pedidos", empresaA, "{\"clienteId\":" + clienteA + ",\"itens\":" + itens + "}", 400);
        }
    }
    @Test void bancoImpedeReferenciasCruzadasMesmoSemApi() throws Exception {
        long id = pedido(empresaA, clienteA).get("id").asLong();
        try (var c = admin()) {
            assertThatThrownBy(() -> {
                try (var s = c.prepareStatement("INSERT INTO tcc.pedido(tenant_id, cliente_id, total) VALUES (?, ?, 1)")) {
                    s.setLong(1, empresaA); s.setLong(2, clienteB); s.executeUpdate();
                }
            }).isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("23503");
            assertThatThrownBy(() -> {
                try (var s = c.prepareStatement("INSERT INTO tcc.item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario) VALUES (?, ?, 'X', 1, 1)")) {
                    s.setLong(1, empresaB); s.setLong(2, id); s.executeUpdate();
                }
            }).isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("23503");
        }
    }
    @Test void runtimeNaoPodeAlterarSchemaOuHistoricoDeMigracoes() throws Exception {
        try (var c = DriverManager.getConnection(POSTGRES.getJdbcUrl(), "tcc_app", "application-test"); var s = c.createStatement()) {
            assertThatThrownBy(() -> s.execute("CREATE TABLE tcc.invasao(id bigint)"))
                    .isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("42501");
            assertThatThrownBy(() -> s.executeQuery("SELECT * FROM tcc.flyway_schema_history"))
                    .isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("42501");
        }
    }
    @Test void geradorProduzBaseConsultavelERecusaLoteRepetido(@org.junit.jupiter.api.io.TempDir java.nio.file.Path temp) throws Exception {
        var output = temp.resolve("seed.sql");
        var process = new ProcessBuilder("python3", "../scripts/gerar_base.py", "--empresas", "2",
                "--clientes-por-empresa", "2", "--pedidos-por-empresa", "5",
                "--lote", "teste-integracao", "--saida", output.toString()).redirectErrorStream(true).start();
        String log = new String(process.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
        assertThat(process.waitFor()).as(log).isZero();
        POSTGRES.copyFileToContainer(org.testcontainers.utility.MountableFile.forHostPath(output), "/tmp/seed.sql");
        var seeded = POSTGRES.execInContainer("psql", "-X", "-U", POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/seed.sql");
        assertThat(seeded.getExitCode()).as(seeded.getStderr()).isZero();
        long tenant;
        try (var c = admin(); var s = c.createStatement();
             var rows = s.executeQuery("SELECT id FROM tcc.empresa WHERE nome = 'TCC-teste-integracao Empresa 1'")) {
            assertThat(rows.next()).isTrue(); tenant = rows.getLong(1);
        }
        var page = body(call("GET", "/api/pedidos?page=1&size=2", tenant, null, 200));
        assertThat(page.get("totalElements").asLong()).isEqualTo(5);
        assertThat(page.get("content").size()).isEqualTo(2);
        var repeated = POSTGRES.execInContainer("psql", "-X", "-U", POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/seed.sql");
        assertThat(repeated.getExitCode()).isNotZero();
        var unchanged = body(call("GET", "/api/pedidos", tenant, null, 200));
        assertThat(unchanged.get("totalElements").asLong()).isEqualTo(5);
    }

}
