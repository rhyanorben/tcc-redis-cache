package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import org.springframework.stereotype.Service;

@Service
public class ConsultaPedidosService {

    private final PaginaCache paginaCache;
    private final PedidoService pedidoService;

    public ConsultaPedidosService(PaginaCache paginaCache, PedidoService pedidoService) {
        this.paginaCache = paginaCache;
        this.pedidoService = pedidoService;
    }

    public PaginaPedidos listar(long tenantId, int pagina, int tamanho) {
        return paginaCache.buscarOuCarregar(
                tenantId,
                pagina,
                tamanho,
                () -> pedidoService.listar(tenantId, pagina, tamanho));
    }
}
