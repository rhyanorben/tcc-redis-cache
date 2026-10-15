package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import java.util.function.Supplier;

public class PaginaCacheDesabilitado implements PaginaCache {

    @Override
    public PaginaPedidos buscarOuCarregar(
            long tenantId,
            int pagina,
            int tamanho,
            Supplier<PaginaPedidos> carregarDoBanco) {
        return carregarDoBanco.get();
    }

    @Override
    public void invalidar(long tenantId) {
    }
}
