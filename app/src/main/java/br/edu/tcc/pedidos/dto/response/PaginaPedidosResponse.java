package br.edu.tcc.pedidos.dto.response;

import java.util.List;

public record PaginaPedidosResponse(
        List<PedidoResumoResponse> content,
        int page,
        int size,
        long totalElements,
        long totalPages,
        boolean first,
        boolean last) {

    public static PaginaPedidosResponse of(
            List<PedidoResumoResponse> pedidos,
            int pagina,
            int tamanho,
            long totalPedidos) {
        long totalPaginas = totalPedidos / tamanho + (totalPedidos % tamanho == 0 ? 0 : 1);
        boolean primeiraPagina = pagina == 0;
        boolean ultimaPagina = (long) pagina + 1 >= totalPaginas;

        return new PaginaPedidosResponse(
                List.copyOf(pedidos),
                pagina,
                tamanho,
                totalPedidos,
                totalPaginas,
                primeiraPagina,
                ultimaPagina);
    }
}
