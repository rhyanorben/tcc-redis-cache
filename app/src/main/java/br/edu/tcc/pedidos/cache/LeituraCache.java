package br.edu.tcc.pedidos.cache;

import br.edu.tcc.pedidos.model.PedidoResumo;
import java.util.Optional;
import org.springframework.data.domain.Page;

record LeituraCache(
        String versao,
        String chavePagina,
        Optional<Page<PedidoResumo>> paginaArmazenada) {
}
