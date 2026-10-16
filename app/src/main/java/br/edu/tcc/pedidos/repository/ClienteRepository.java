package br.edu.tcc.pedidos.repository;

import br.edu.tcc.pedidos.model.Cliente;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ClienteRepository extends JpaRepository<Cliente, Long> {

    @Query("""
            SELECT c FROM Cliente c
            WHERE c.tenantId = :tenantId AND c.id = :clienteId
            """)
    Optional<Cliente> buscarDaEmpresa(@Param("tenantId") long tenantId, @Param("clienteId") long clienteId);
}
