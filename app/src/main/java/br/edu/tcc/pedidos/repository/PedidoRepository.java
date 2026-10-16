package br.edu.tcc.pedidos.repository;

import br.edu.tcc.pedidos.model.Pedido;
import br.edu.tcc.pedidos.model.PedidoResumo;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PedidoRepository extends JpaRepository<Pedido, Long> {

    @Query(value = """
            SELECT new br.edu.tcc.pedidos.model.PedidoResumo(
                p.id, c.id, c.nome, p.status, p.total, p.criadoEm)
            FROM Pedido p
            JOIN p.cliente c
            WHERE p.tenantId = :tenantId AND c.tenantId = :tenantId
            """, countQuery = """
            SELECT count(p) FROM Pedido p
            WHERE p.tenantId = :tenantId
            """)
    Page<PedidoResumo> listarDaEmpresa(@Param("tenantId") long tenantId, Pageable pageable);

    @Query("""
            SELECT p FROM Pedido p
            JOIN FETCH p.cliente c
            WHERE p.tenantId = :tenantId
              AND c.tenantId = :tenantId
              AND p.id = :pedidoId
            """)
    Optional<Pedido> buscarDaEmpresa(@Param("tenantId") long tenantId, @Param("pedidoId") long pedidoId);
}
