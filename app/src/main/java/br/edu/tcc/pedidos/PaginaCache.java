package br.edu.tcc.pedidos;

import java.util.function.Supplier;
import static br.edu.tcc.pedidos.Contratos.PaginaPedidos;

public interface PaginaCache {
    PaginaPedidos buscarOuCarregar(long tenant, int page, int size, Supplier<PaginaPedidos> banco);
    void invalidar(long tenant);
}
