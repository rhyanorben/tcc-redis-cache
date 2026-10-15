package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.AlterarStatus;
import br.edu.tcc.pedidos.Contratos.Cliente;
import br.edu.tcc.pedidos.Contratos.Empresa;
import br.edu.tcc.pedidos.Contratos.NovaEmpresa;
import br.edu.tcc.pedidos.Contratos.NovoCliente;
import br.edu.tcc.pedidos.Contratos.NovoPedido;
import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import br.edu.tcc.pedidos.Contratos.PedidoResumo;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PedidoService {

    private final PedidoRepository pedidoRepository;
    private final ApplicationEventPublisher eventPublisher;

    public PedidoService(PedidoRepository pedidoRepository, ApplicationEventPublisher eventPublisher) {
        this.pedidoRepository = pedidoRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Empresa criarEmpresa(NovaEmpresa novaEmpresa) {
        return pedidoRepository.criarEmpresa(novaEmpresa.nome().trim());
    }

    @Transactional
    public Cliente criarCliente(long tenantId, NovoCliente novoCliente) {
        exigirEmpresaExistente(tenantId);
        return pedidoRepository.criarCliente(tenantId, novoCliente.nome().trim());
    }

    @Transactional
    public PedidoResumo criarPedido(long tenantId, NovoPedido novoPedido) {
        exigirEmpresaExistente(tenantId);
        exigirClienteDaEmpresa(tenantId, novoPedido.clienteId());

        long pedidoId = pedidoRepository.criarPedido(tenantId, novoPedido);
        var pedido = pedidoRepository.buscar(tenantId, pedidoId);
        publicarAlteracaoPedidos(tenantId);
        return pedido;
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public PaginaPedidos listar(long tenantId, int pagina, int tamanho) {
        exigirEmpresaExistente(tenantId);

        var pedidos = pedidoRepository.listar(tenantId, pagina, tamanho);
        long totalPedidos = pedidoRepository.contar(tenantId);
        return PaginaPedidos.of(pedidos, pagina, tamanho, totalPedidos);
    }

    @Transactional
    public PedidoResumo alterarStatus(long tenantId, long pedidoId, AlterarStatus alteracao) {
        int pedidosAtualizados = pedidoRepository.alterarStatus(tenantId, pedidoId, alteracao.status());
        if (pedidosAtualizados == 0) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Pedido não encontrado nesta empresa");
        }

        var pedidoAtualizado = pedidoRepository.buscar(tenantId, pedidoId);
        publicarAlteracaoPedidos(tenantId);
        return pedidoAtualizado;
    }

    private void exigirEmpresaExistente(long tenantId) {
        if (!pedidoRepository.empresaExiste(tenantId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Empresa não encontrada");
        }
    }

    private void exigirClienteDaEmpresa(long tenantId, long clienteId) {
        if (!pedidoRepository.clienteExiste(tenantId, clienteId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Cliente não encontrado nesta empresa");
        }
    }

    private void publicarAlteracaoPedidos(long tenantId) {
        eventPublisher.publishEvent(new PedidosAlterados(tenantId));
    }
}
