package br.edu.tcc.pedidos;

import org.springframework.stereotype.Service;
import static br.edu.tcc.pedidos.Contratos.PaginaPedidos;

@Service
public class ConsultaPedidosService {
    private final PaginaCache cache;
    private final PedidoService pedidos;
    public ConsultaPedidosService(PaginaCache cache, PedidoService pedidos) {
        this.cache = cache;
        this.pedidos = pedidos;
    }
    public PaginaPedidos listar(long tenant, int page, int size) {
        // A transação PostgreSQL começa somente na falta do cache.
        return cache.buscarOuCarregar(tenant, page, size, () -> pedidos.listar(tenant, page, size));
    }
}
