package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.cache.PaginaCache;
import br.edu.tcc.pedidos.model.PedidoResumo;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConsultaPedidosService {

    private final PaginaCache paginaCache;
    private final PedidoService pedidoService;

    public ConsultaPedidosService(PaginaCache paginaCache, PedidoService pedidoService) {
        this.paginaCache = paginaCache;
        this.pedidoService = pedidoService;
    }

    @Transactional(readOnly = true)
    public Page<PedidoResumo> listar(long tenantId, Pageable pageable) {
        return paginaCache.buscarOuCarregar(tenantId, pageable, () -> pedidoService.listar(tenantId, pageable));
    }
}
