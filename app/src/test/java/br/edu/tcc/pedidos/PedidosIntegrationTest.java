package br.edu.tcc.pedidos;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.commons.lang3.ObjectUtils;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PedidosIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(
            DockerImageName.parse("postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826"))
            .withInitScript("bootstrap.sql");

    @Autowired
    ApplicationContext contexto;

    @LocalServerPort
    int porta;

    private final HttpClient clienteHttp = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();
    private long empresaPrincipalId;
    private long outraEmpresaId;
    private long clientePrincipalId;
    private long clienteOutraEmpresaId;

    @DynamicPropertySource
    static void configurarAplicacao(DynamicPropertyRegistry propriedades) {
        propriedades.add("app.cache.enabled", () -> false);
        propriedades.add("spring.datasource.url", () -> POSTGRES.getJdbcUrl() + "&currentSchema=tcc");
        propriedades.add("spring.datasource.username", () -> "tcc_app");
        propriedades.add("spring.datasource.password", () -> "application-test");
        propriedades.add("DB_PASSWORD", () -> "application-test");
        propriedades.add("spring.flyway.enabled", () -> true);
        propriedades.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        propriedades.add("spring.flyway.user", () -> "tcc_migrator");
        propriedades.add("spring.flyway.password", () -> "migration-test");
    }

    @BeforeEach
    void criarEmpresasEClientes() throws Exception {
        empresaPrincipalId = criarEmpresa("Empresa A");
        outraEmpresaId = criarEmpresa("Empresa B");
        clientePrincipalId = criarCliente(empresaPrincipalId, "Cliente A");
        clienteOutraEmpresaId = criarCliente(outraEmpresaId, "Cliente B");
    }

    @Test
    void paginacaoIsolaEmpresaEContagem() throws Exception {
        JsonNode primeiroPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode segundoPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        criarPedido(outraEmpresaId, clienteOutraEmpresaId);

        JsonNode primeiraPagina = listarPedidos(empresaPrincipalId, "page=0&size=1");
        JsonNode segundaPagina = listarPedidos(empresaPrincipalId, "page=1&size=1");

        assertThat(primeiraPagina.get("totalElements").asLong()).isEqualTo(2);
        assertThat(primeiraPagina.get("totalPages").asLong()).isEqualTo(2);
        assertThat(primeiraPagina.get("content").get(0).get("id").asLong())
                .isEqualTo(segundoPedido.get("id").asLong());
        assertThat(segundaPagina.get("content").get(0).get("id").asLong())
                .isEqualTo(primeiroPedido.get("id").asLong());
        assertThat(segundaPagina.get("last").asBoolean()).isTrue();
        assertThat(primeiraPagina.get("content").get(0).get("total").decimalValue())
                .isEqualByComparingTo(new BigDecimal("24.70"));
    }

    @Test
    void desempataPedidosComMesmoHorarioPorId() throws Exception {
        JsonNode primeiroPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode segundoPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        String atualizacao = "UPDATE tcc.pedido SET criado_em = '2026-01-01T00:00:00Z' WHERE tenant_id = ?";

        try (Connection conexao = conectarComoAdministrador();
             PreparedStatement comando = conexao.prepareStatement(atualizacao)) {
            comando.setLong(1, empresaPrincipalId);
            comando.executeUpdate();
        }

        JsonNode pagina = listarPedidos(empresaPrincipalId, "size=2");

        assertThat(pagina.get("content").get(0).get("id").asLong())
                .isEqualTo(segundoPedido.get("id").asLong());
        assertThat(pagina.get("content").get(1).get("id").asLong())
                .isEqualTo(primeiroPedido.get("id").asLong());
    }

    @Test
    void rejeitaClienteDeOutraEmpresaSemCriarPedidoOuItens() throws Exception {
        enviarRequisicao("POST", "/api/pedidos", empresaPrincipalId, corpoNovoPedido(clienteOutraEmpresaId), 404);

        JsonNode pagina = listarPedidos(empresaPrincipalId, "");

        assertThat(pagina.get("totalElements").asLong()).isZero();

        String consulta = "SELECT count(*) FROM tcc.item_pedido WHERE tenant_id = ?";
        try (Connection conexao = conectarComoAdministrador();
             PreparedStatement comando = conexao.prepareStatement(consulta)) {
            comando.setLong(1, empresaPrincipalId);
            try (ResultSet resultado = comando.executeQuery()) {
                assertThat(resultado.next()).isTrue();
                assertThat(resultado.getLong(1)).isZero();
            }
        }
    }

    @Test
    void atualizacaoNaoAtravessaEmpresas() throws Exception {
        long pedidoId = criarPedido(empresaPrincipalId, clientePrincipalId).get("id").asLong();
        String caminhoStatus = "/api/pedidos/" + pedidoId + "/status";

        enviarRequisicao("PATCH", caminhoStatus, outraEmpresaId, "{\"status\":\"CANCELADO\"}", 404);
        JsonNode pagina = listarPedidos(empresaPrincipalId, "");

        assertThat(pagina.get("content").get(0).get("status").asText()).isEqualTo("ABERTO");

        JsonNode pedidoAtualizado = lerCorpo(enviarRequisicao(
                "PATCH", caminhoStatus, empresaPrincipalId, "{\"status\":\"CONFIRMADO\"}", 200));

        assertThat(pedidoAtualizado.get("status").asText()).isEqualTo("CONFIRMADO");
    }

    @Test
    void exigeTenantEValidaLimites() throws Exception {
        enviarRequisicao("GET", "/api/pedidos", null, null, 400);
        enviarRequisicao("GET", "/api/pedidos", 0L, null, 400);

        for (String parametros : List.of("page=-1", "size=0", "size=101", "page=1000001", "page=abc")) {
            enviarRequisicao("GET", "/api/pedidos?" + parametros, empresaPrincipalId, null, 400);
        }

        enviarRequisicao("GET", "/api/pedidos", Long.MAX_VALUE, null, 404);
    }

    @Test
    void paginasVaziasTemMetadadosConsistentes() throws Exception {
        JsonNode paginaVazia = listarPedidos(empresaPrincipalId, "");

        assertThat(paginaVazia.get("totalElements").asLong()).isZero();
        assertThat(paginaVazia.get("totalPages").asLong()).isZero();
        assertThat(paginaVazia.get("first").asBoolean()).isTrue();
        assertThat(paginaVazia.get("last").asBoolean()).isTrue();

        criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode paginaAlemDoTotal = listarPedidos(empresaPrincipalId, "page=10&size=1");

        assertThat(paginaAlemDoTotal.get("content").size()).isZero();
        assertThat(paginaAlemDoTotal.get("totalElements").asLong()).isEqualTo(1);
    }

    @Test
    void validaItensEPrecisaoMonetaria() throws Exception {
        List<String> itensInvalidos = List.of(
                "[]",
                "[null]",
                "[{\"descricao\":\"A\",\"quantidade\":0,\"precoUnitario\":1}]",
                "[{\"descricao\":\"A\",\"quantidade\":1,\"precoUnitario\":1.001}]");

        for (String itens : itensInvalidos) {
            String corpo = "{\"clienteId\":" + clientePrincipalId + ",\"itens\":" + itens + "}";
            enviarRequisicao("POST", "/api/pedidos", empresaPrincipalId, corpo, 400);
        }
    }

    @Test
    void bancoImpedeReferenciasCruzadasMesmoSemApi() throws Exception {
        long pedidoId = criarPedido(empresaPrincipalId, clientePrincipalId).get("id").asLong();
        String insercaoPedido = "INSERT INTO tcc.pedido(tenant_id, cliente_id, total) VALUES (?, ?, 1)";
        String insercaoItem = """
                INSERT INTO tcc.item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario)
                VALUES (?, ?, 'X', 1, 1)
                """;

        try (Connection conexao = conectarComoAdministrador()) {
            assertThatThrownBy(() -> {
                try (PreparedStatement comando = conexao.prepareStatement(insercaoPedido)) {
                    comando.setLong(1, empresaPrincipalId);
                    comando.setLong(2, clienteOutraEmpresaId);
                    comando.executeUpdate();
                }
            }).isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("23503");

            assertThatThrownBy(() -> {
                try (PreparedStatement comando = conexao.prepareStatement(insercaoItem)) {
                    comando.setLong(1, outraEmpresaId);
                    comando.setLong(2, pedidoId);
                    comando.executeUpdate();
                }
            }).isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("23503");
        }
    }

    @Test
    void runtimeNaoPodeAlterarSchemaOuHistoricoDeMigracoes() throws Exception {
        try (Connection conexao = DriverManager.getConnection(POSTGRES.getJdbcUrl(), "tcc_app", "application-test");
             Statement comando = conexao.createStatement()) {
            assertThatThrownBy(() -> comando.execute("CREATE TABLE tcc.invasao(id bigint)"))
                    .isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("42501");
            assertThatThrownBy(() -> comando.executeQuery("SELECT * FROM tcc.flyway_schema_history"))
                    .isInstanceOf(SQLException.class).extracting("SQLState").isEqualTo("42501");
        }
    }

    @Test
    void geradorProduzBaseConsultavelERecusaLoteRepetido(@TempDir Path diretorioTemporario) throws Exception {
        Path arquivoBase = diretorioTemporario.resolve("seed.sql");
        gerarBaseDeTeste(arquivoBase);
        POSTGRES.copyFileToContainer(MountableFile.forHostPath(arquivoBase), "/tmp/seed.sql");

        ExecResult primeiraImportacao = importarBaseDeTeste();

        assertThat(primeiraImportacao.getExitCode()).as(primeiraImportacao.getStderr()).isZero();

        long empresaGeradaId = buscarEmpresaGerada();
        JsonNode pagina = listarPedidos(empresaGeradaId, "page=1&size=2");

        assertThat(pagina.get("totalElements").asLong()).isEqualTo(5);
        assertThat(pagina.get("content").size()).isEqualTo(2);

        ExecResult importacaoRepetida = importarBaseDeTeste();

        assertThat(importacaoRepetida.getExitCode()).isNotZero();
        assertThat(listarPedidos(empresaGeradaId, "").get("totalElements").asLong()).isEqualTo(5);
    }

    @Test
    void modoSemCacheNaoCriaConexaoRedis() {
        assertThat(contexto.getBeansOfType(RedisConnectionFactory.class)).isEmpty();
    }

    @Test
    void contratosHttpPreservamCamposPublicosSemExporEntidades() throws Exception {
        JsonNode empresa = lerCorpo(enviarRequisicao(
                "POST", "/api/empresas", null, "{\"nome\":\"Empresa contrato\"}", 201));
        long empresaId = empresa.get("id").asLong();
        JsonNode cliente = lerCorpo(enviarRequisicao(
                "POST", "/api/clientes", empresaId, "{\"nome\":\"Cliente contrato\"}", 201));
        JsonNode pedido = criarPedido(empresaId, cliente.get("id").asLong());
        JsonNode pagina = listarPedidos(empresaId, "");

        assertThat(nomesDosCampos(empresa)).containsExactlyInAnyOrder("id", "nome");
        assertThat(nomesDosCampos(cliente)).containsExactlyInAnyOrder("id", "tenantId", "nome");
        assertThat(nomesDosCampos(pedido)).containsExactlyInAnyOrder(
                "id", "clienteId", "clienteNome", "status", "total", "criadoEm");
        assertThat(nomesDosCampos(pagina)).containsExactlyInAnyOrder(
                "content", "page", "size", "totalElements", "totalPages", "first", "last");
        assertThat(pagina.get("content").get(0)).isEqualTo(pedido);
    }

    @Test
    void pageableUsaValoresPadraoEOrdenacaoDecrescenteEstavel() throws Exception {
        criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode pedidoMaisRecente = criarPedido(empresaPrincipalId, clientePrincipalId);

        JsonNode pagina = listarPedidos(empresaPrincipalId, "");

        assertThat(pagina.get("page").asInt()).isZero();
        assertThat(pagina.get("size").asInt()).isEqualTo(20);
        assertThat(pagina.get("totalElements").asLong()).isEqualTo(2);
        assertThat(pagina.get("content").get(0).get("id")).isEqualTo(pedidoMaisRecente.get("id"));
    }

    @Test
    void pageablePreservaOrdenacaoSolicitadaEntrePaginas() throws Exception {
        JsonNode primeiroPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode segundoPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode terceiroPedido = criarPedido(empresaPrincipalId, clientePrincipalId);

        JsonNode primeiraPagina = listarPedidos(empresaPrincipalId, "page=0&size=2&sort=id,asc");
        JsonNode segundaPagina = listarPedidos(empresaPrincipalId, "page=1&size=2&sort=id,asc");

        assertThat(primeiraPagina.get("content").get(0).get("id")).isEqualTo(primeiroPedido.get("id"));
        assertThat(primeiraPagina.get("content").get(1).get("id")).isEqualTo(segundoPedido.get("id"));
        assertThat(segundaPagina.get("content").get(0).get("id")).isEqualTo(terceiroPedido.get("id"));
        assertThat(segundaPagina.get("totalElements").asLong()).isEqualTo(3);
        assertThat(segundaPagina.get("totalPages").asLong()).isEqualTo(2);
        assertThat(segundaPagina.get("last").asBoolean()).isTrue();
    }

    @Test
    void ordenacaoPorTotalIncluiIdParaDesempatarPedidos() throws Exception {
        JsonNode primeiroPedido = criarPedido(empresaPrincipalId, clientePrincipalId);
        JsonNode segundoPedido = criarPedido(empresaPrincipalId, clientePrincipalId);

        JsonNode primeiraPagina = listarPedidos(empresaPrincipalId, "size=1&sort=total,asc");
        JsonNode segundaPagina = listarPedidos(empresaPrincipalId, "page=1&size=1&sort=total,asc");

        assertThat(primeiraPagina.get("content").get(0).get("id")).isEqualTo(segundoPedido.get("id"));
        assertThat(segundaPagina.get("content").get(0).get("id")).isEqualTo(primeiroPedido.get("id"));
    }

    @Test
    void rejeitaCamposEDirecoesDeOrdenacaoForaDoContrato() throws Exception {
        for (String parametros : List.of(
                "sort=clienteNome,asc",
                "sort=tenantId,asc",
                "sort=cliente.nome,asc",
                "sort=criado_em,desc",
                "sort=id,invalido")) {
            enviarRequisicao("GET", "/api/pedidos?" + parametros, empresaPrincipalId, null, 400);
        }
    }

    @Test
    void tenantIdEObrigatorioMesmoQuandoCabecalhoAntigoEstaPresente() throws Exception {
        HttpRequest requisicao = HttpRequest.newBuilder(URI.create("http://localhost:" + porta + "/api/pedidos"))
                .header("X-Tenant-Id", Long.toString(empresaPrincipalId))
                .GET()
                .build();

        HttpResponse<String> resposta = clienteHttp.send(requisicao, HttpResponse.BodyHandlers.ofString());

        assertThat(resposta.statusCode()).isEqualTo(400);
    }

    private long criarEmpresa(String nome) throws Exception {
        String corpo = json.writeValueAsString(Map.of("nome", nome));
        return lerCorpo(enviarRequisicao("POST", "/api/empresas", null, corpo, 201)).get("id").asLong();
    }

    private long criarCliente(long empresaId, String nome) throws Exception {
        String corpo = json.writeValueAsString(Map.of("nome", nome));
        return lerCorpo(enviarRequisicao("POST", "/api/clientes", empresaId, corpo, 201)).get("id").asLong();
    }

    private JsonNode criarPedido(long empresaId, long clienteId) throws Exception {
        return lerCorpo(enviarRequisicao("POST", "/api/pedidos", empresaId, corpoNovoPedido(clienteId), 201));
    }

    private String corpoNovoPedido(long clienteId) {
        return """
                {"clienteId":%d,"itens":[{"descricao":"Item","quantidade":2,"precoUnitario":12.35}]}
                """.formatted(clienteId);
    }

    private JsonNode listarPedidos(long empresaId, String parametros) throws Exception {
        String caminho = parametros.isEmpty() ? "/api/pedidos" : "/api/pedidos?" + parametros;
        return lerCorpo(enviarRequisicao("GET", caminho, empresaId, null, 200));
    }

    private HttpResponse<String> enviarRequisicao(
            String metodo, String caminho, Long empresaId, String corpo, int statusEsperado) throws Exception {
        HttpRequest.BodyPublisher conteudo = ObjectUtils.isEmpty(corpo)
                ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(corpo);
        HttpRequest.Builder requisicao = HttpRequest.newBuilder(URI.create("http://localhost:" + porta + caminho))
                .header("Content-Type", "application/json")
                .method(metodo, conteudo);

        if (ObjectUtils.isNotEmpty(empresaId)) {
            requisicao.header("tenantId", empresaId.toString());
        }

        HttpResponse<String> resposta = clienteHttp.send(requisicao.build(), HttpResponse.BodyHandlers.ofString());
        assertThat(resposta.statusCode()).as(resposta.body()).isEqualTo(statusEsperado);
        return resposta;
    }

    private JsonNode lerCorpo(HttpResponse<String> resposta) throws Exception {
        return json.readTree(resposta.body());
    }

    private Set<String> nomesDosCampos(JsonNode objeto) {
        Set<String> campos = new HashSet<String>();
        objeto.fieldNames().forEachRemaining(campos::add);
        return campos;
    }

    private Connection conectarComoAdministrador() throws SQLException {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }

    private void gerarBaseDeTeste(Path arquivoBase) throws Exception {
        Process processo = new ProcessBuilder(
                "python3", "../scripts/gerar_base.py",
                "--empresas", "2",
                "--clientes-por-empresa", "2",
                "--pedidos-por-empresa", "5",
                "--lote", "teste-integracao",
                "--saida", arquivoBase.toString())
                .redirectErrorStream(true)
                .start();
        String saida = new String(processo.getInputStream().readAllBytes(), StandardCharsets.UTF_8);

        assertThat(processo.waitFor()).as(saida).isZero();
    }

    private ExecResult importarBaseDeTeste() throws Exception {
        return POSTGRES.execInContainer(
                "psql", "-X", "-U", POSTGRES.getUsername(), "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/seed.sql");
    }

    private long buscarEmpresaGerada() throws SQLException {
        String consulta = "SELECT id FROM tcc.empresa WHERE nome = 'TCC-teste-integracao Empresa 1'";
        try (Connection conexao = conectarComoAdministrador();
             Statement comando = conexao.createStatement();
             ResultSet resultado = comando.executeQuery(consulta)) {
            assertThat(resultado.next()).isTrue();
            return resultado.getLong(1);
        }
    }
}
