package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.Cliente;
import br.edu.tcc.pedidos.Contratos.Empresa;
import br.edu.tcc.pedidos.Contratos.NovoItem;
import br.edu.tcc.pedidos.Contratos.NovoPedido;
import br.edu.tcc.pedidos.Contratos.PedidoResumo;
import br.edu.tcc.pedidos.Contratos.Status;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class PedidoRepository {

    private static final String CONSULTA_RESUMO_PEDIDO = """
            SELECT pedido.id, pedido.cliente_id, cliente.nome AS cliente_nome,
                   pedido.status, pedido.total, pedido.criado_em
            FROM pedido
            JOIN cliente ON cliente.tenant_id = pedido.tenant_id AND cliente.id = pedido.cliente_id
            """;

    private final JdbcTemplate jdbcTemplate;

    public PedidoRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public boolean empresaExiste(long tenantId) {
        String consulta = "SELECT EXISTS (SELECT 1 FROM empresa WHERE id = ?)";
        return Boolean.TRUE.equals(jdbcTemplate.queryForObject(consulta, Boolean.class, tenantId));
    }

    public Empresa criarEmpresa(String nome) {
        String insercao = "INSERT INTO empresa(nome) VALUES (?) RETURNING id, nome";
        return jdbcTemplate.queryForObject(insercao, this::mapearEmpresa, nome);
    }

    public Cliente criarCliente(long tenantId, String nome) {
        String insercao = """
                INSERT INTO cliente(tenant_id, nome)
                VALUES (?, ?)
                RETURNING id, tenant_id, nome
                """;
        return jdbcTemplate.queryForObject(insercao, this::mapearCliente, tenantId, nome);
    }

    public boolean clienteExiste(long tenantId, long clienteId) {
        String consulta = "SELECT EXISTS (SELECT 1 FROM cliente WHERE tenant_id = ? AND id = ?)";
        return Boolean.TRUE.equals(jdbcTemplate.queryForObject(consulta, Boolean.class, tenantId, clienteId));
    }

    public long criarPedido(long tenantId, NovoPedido novoPedido) {
        String insercao = """
                INSERT INTO pedido(tenant_id, cliente_id, total)
                VALUES (?, ?, ?)
                RETURNING id
                """;
        BigDecimal total = calcularTotal(novoPedido.itens());
        Long pedidoId = jdbcTemplate.queryForObject(insercao, Long.class, tenantId, novoPedido.clienteId(), total);

        inserirItens(tenantId, pedidoId, novoPedido.itens());
        return pedidoId;
    }

    public PedidoResumo buscar(long tenantId, long pedidoId) {
        String consulta = CONSULTA_RESUMO_PEDIDO + "WHERE pedido.tenant_id = ? AND pedido.id = ?";
        return jdbcTemplate.queryForObject(consulta, this::mapearPedidoResumo, tenantId, pedidoId);
    }

    public List<PedidoResumo> listar(long tenantId, int pagina, int tamanho) {
        String consulta = CONSULTA_RESUMO_PEDIDO + """
                WHERE pedido.tenant_id = ?
                ORDER BY pedido.criado_em DESC, pedido.id DESC
                LIMIT ? OFFSET ?
                """;
        long deslocamento = (long) pagina * tamanho;
        return jdbcTemplate.query(consulta, this::mapearPedidoResumo, tenantId, tamanho, deslocamento);
    }

    public long contar(long tenantId) {
        String consulta = "SELECT count(*) FROM pedido WHERE tenant_id = ?";
        return jdbcTemplate.queryForObject(consulta, Long.class, tenantId);
    }

    public int alterarStatus(long tenantId, long pedidoId, Status status) {
        String atualizacao = """
                UPDATE pedido
                SET status = ?, atualizado_em = now()
                WHERE tenant_id = ? AND id = ?
                """;
        return jdbcTemplate.update(atualizacao, status.name(), tenantId, pedidoId);
    }

    private BigDecimal calcularTotal(List<NovoItem> itens) {
        return itens.stream()
                .map(item -> item.precoUnitario().multiply(BigDecimal.valueOf(item.quantidade())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private void inserirItens(long tenantId, long pedidoId, List<NovoItem> itens) {
        String insercao = """
                INSERT INTO item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario)
                VALUES (?, ?, ?, ?, ?)
                """;
        jdbcTemplate.batchUpdate(insercao, itens, 100, (statement, item) -> {
            statement.setLong(1, tenantId);
            statement.setLong(2, pedidoId);
            statement.setString(3, item.descricao().trim());
            statement.setInt(4, item.quantidade());
            statement.setBigDecimal(5, item.precoUnitario());
        });
    }

    private Empresa mapearEmpresa(ResultSet resultado, int numeroLinha) throws SQLException {
        return new Empresa(resultado.getLong("id"), resultado.getString("nome"));
    }

    private Cliente mapearCliente(ResultSet resultado, int numeroLinha) throws SQLException {
        return new Cliente(
                resultado.getLong("id"),
                resultado.getLong("tenant_id"),
                resultado.getString("nome"));
    }

    private PedidoResumo mapearPedidoResumo(ResultSet resultado, int numeroLinha) throws SQLException {
        return new PedidoResumo(
                resultado.getLong("id"),
                resultado.getLong("cliente_id"),
                resultado.getString("cliente_nome"),
                Status.valueOf(resultado.getString("status")),
                resultado.getBigDecimal("total"),
                resultado.getObject("criado_em", OffsetDateTime.class));
    }
}
