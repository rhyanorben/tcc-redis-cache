package br.edu.tcc.pedidos;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class InvalidacaoPedidos {

    private final PaginaCache paginaCache;

    public InvalidacaoPedidos(PaginaCache paginaCache) {
        this.paginaCache = paginaCache;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void depoisDoCommit(PedidosAlterados pedidosAlterados) {
        paginaCache.invalidar(pedidosAlterados.tenantId());
    }
}
