package br.edu.tcc.pedidos;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class InvalidacaoPedidos {
    private final PaginaCache cache;
    public InvalidacaoPedidos(PaginaCache cache) { this.cache = cache; }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void depoisDoCommit(PedidosAlterados event) {
        cache.invalidar(event.tenantId());
    }
}
