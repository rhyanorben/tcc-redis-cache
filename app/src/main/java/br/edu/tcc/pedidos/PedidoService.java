package br.edu.tcc.pedidos;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static br.edu.tcc.pedidos.Contratos.*;

@Service
public class PedidoService {
    private final PedidoRepository repository;
    public PedidoService(PedidoRepository repository) { this.repository = repository; }

    private void exigirEmpresa(long tenant) {
        if (!repository.empresaExiste(tenant)) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Empresa não encontrada");
    }
    @Transactional
    public Empresa criarEmpresa(NovaEmpresa request) { return repository.criarEmpresa(request.nome().trim()); }
    @Transactional
    public Cliente criarCliente(long tenant, NovoCliente request) {
        exigirEmpresa(tenant);
        return repository.criarCliente(tenant, request.nome().trim());
    }
    @Transactional
    public PedidoResumo criarPedido(long tenant, NovoPedido request) {
        exigirEmpresa(tenant);
        if (!repository.clienteExiste(tenant, request.clienteId()))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Cliente não encontrado nesta empresa");
        return repository.buscar(tenant, repository.criarPedido(tenant, request));
    }
    // Conteúdo e contagem observam o mesmo snapshot, inclusive sob escritas concorrentes.
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public PaginaPedidos listar(long tenant, int page, int size) {
        exigirEmpresa(tenant);
        return PaginaPedidos.of(repository.listar(tenant, page, size), page, size, repository.contar(tenant));
    }
    @Transactional
    public PedidoResumo alterarStatus(long tenant, long pedido, AlterarStatus request) {
        if (repository.alterarStatus(tenant, pedido, request.status()) == 0)
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Pedido não encontrado nesta empresa");
        return repository.buscar(tenant, pedido);
    }
}
