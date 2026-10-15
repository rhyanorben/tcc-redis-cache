package br.edu.tcc.pedidos;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import static br.edu.tcc.pedidos.Contratos.*;

@Repository
public class PedidoRepository {
    private final JdbcTemplate jdbc;
    public PedidoRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public boolean empresaExiste(long tenant) {
        return Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS (SELECT 1 FROM empresa WHERE id = ?)", Boolean.class, tenant));
    }
    public Empresa criarEmpresa(String nome) {
        return jdbc.queryForObject("INSERT INTO empresa(nome) VALUES (?) RETURNING id, nome",
                (rs, row) -> new Empresa(rs.getLong("id"), rs.getString("nome")), nome);
    }
    public Cliente criarCliente(long tenant, String nome) {
        return jdbc.queryForObject("INSERT INTO cliente(tenant_id, nome) VALUES (?, ?) RETURNING id, tenant_id, nome",
                (rs, row) -> new Cliente(rs.getLong("id"), rs.getLong("tenant_id"), rs.getString("nome")), tenant, nome);
    }
    public boolean clienteExiste(long tenant, long cliente) {
        return Boolean.TRUE.equals(jdbc.queryForObject("SELECT EXISTS (SELECT 1 FROM cliente WHERE tenant_id = ? AND id = ?)", Boolean.class, tenant, cliente));
    }
    public long criarPedido(long tenant, NovoPedido request) {
        var total = request.itens().stream()
                .map(i -> i.precoUnitario().multiply(java.math.BigDecimal.valueOf(i.quantidade())))
                .reduce(java.math.BigDecimal.ZERO, java.math.BigDecimal::add);
        Long id = jdbc.queryForObject("INSERT INTO pedido(tenant_id, cliente_id, total) VALUES (?, ?, ?) RETURNING id",
                Long.class, tenant, request.clienteId(), total);
        jdbc.batchUpdate("INSERT INTO item_pedido(tenant_id, pedido_id, descricao, quantidade, preco_unitario) VALUES (?, ?, ?, ?, ?)",
                request.itens(), 100, (ps, item) -> {
                    ps.setLong(1, tenant); ps.setLong(2, id); ps.setString(3, item.descricao().trim());
                    ps.setInt(4, item.quantidade()); ps.setBigDecimal(5, item.precoUnitario());
                });
        return id;
    }
    private static final String RESUMO = """
            SELECT p.id, p.cliente_id, c.nome AS cliente_nome, p.status, p.total, p.criado_em
            FROM pedido p JOIN cliente c ON c.tenant_id = p.tenant_id AND c.id = p.cliente_id
            """;
    private PedidoResumo map(ResultSet rs, int row) throws SQLException {
        return new PedidoResumo(rs.getLong("id"), rs.getLong("cliente_id"), rs.getString("cliente_nome"),
                Status.valueOf(rs.getString("status")), rs.getBigDecimal("total"),
                rs.getObject("criado_em", java.time.OffsetDateTime.class));
    }
    public PedidoResumo buscar(long tenant, long id) {
        return jdbc.queryForObject(RESUMO + " WHERE p.tenant_id = ? AND p.id = ?", this::map, tenant, id);
    }
    public List<PedidoResumo> listar(long tenant, int page, int size) {
        return jdbc.query(RESUMO + " WHERE p.tenant_id = ? ORDER BY p.criado_em DESC, p.id DESC LIMIT ? OFFSET ?",
                this::map, tenant, size, (long) page * size);
    }
    public long contar(long tenant) {
        return jdbc.queryForObject("SELECT count(*) FROM pedido WHERE tenant_id = ?", Long.class, tenant);
    }
    public int alterarStatus(long tenant, long id, Status status) {
        return jdbc.update("UPDATE pedido SET status = ?, atualizado_em = now() WHERE tenant_id = ? AND id = ?",
                status.name(), tenant, id);
    }
}
