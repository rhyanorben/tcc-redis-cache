package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import java.util.function.Supplier;

public interface PaginaCache {

    PaginaPedidos buscarOuCarregar(long tenantId, int pagina, int tamanho, Supplier<PaginaPedidos> carregarDoBanco);

    void invalidar(long tenantId);
}
