package br.edu.tcc.pedidos.cache;

import br.edu.tcc.pedidos.model.PedidoResumo;
import java.util.function.Supplier;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface PaginaCache {

    Page<PedidoResumo> buscarOuCarregar(
            long tenantId,
            Pageable pageable,
            Supplier<Page<PedidoResumo>> carregarDoBanco);

    void invalidar(long tenantId);
}
