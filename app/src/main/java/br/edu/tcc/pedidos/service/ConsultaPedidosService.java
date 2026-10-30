package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.cache.PaginaCache;
import br.edu.tcc.pedidos.model.PedidoResumo;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class ConsultaPedidosService {

    private final PaginaCache paginaCache;
    private final PedidoService pedidoService;
    private final ControleAcessoBanco controleAcessoBanco;

    public ConsultaPedidosService(
            PaginaCache paginaCache,
            PedidoService pedidoService,
            ControleAcessoBanco controleAcessoBanco) {
        this.paginaCache = paginaCache;
        this.pedidoService = pedidoService;
        this.controleAcessoBanco = controleAcessoBanco;
    }

    public Page<PedidoResumo> listar(long tenantId, Pageable pageable) {
        return paginaCache.buscarOuCarregar(
                tenantId, pageable,
                () -> controleAcessoBanco.executar(() -> pedidoService.listar(tenantId, pageable)));
    }
}
