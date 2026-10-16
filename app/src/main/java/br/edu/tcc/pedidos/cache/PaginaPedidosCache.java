package br.edu.tcc.pedidos.cache;

import br.edu.tcc.pedidos.model.PedidoResumo;
import java.util.List;

record PaginaPedidosCache(List<PedidoResumo> content, long totalElements) {

    PaginaPedidosCache {
        content = List.copyOf(content);
    }
}
