package br.edu.tcc.pedidos.repository;

import br.edu.tcc.pedidos.model.Empresa;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EmpresaRepository extends JpaRepository<Empresa, Long> {
}
