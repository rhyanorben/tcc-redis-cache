package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.event.PedidosAlterados;
import br.edu.tcc.pedidos.model.Cliente;
import br.edu.tcc.pedidos.model.ItemPedido;
import br.edu.tcc.pedidos.model.Pedido;
import br.edu.tcc.pedidos.model.PedidoResumo;
import br.edu.tcc.pedidos.model.StatusPedido;
import br.edu.tcc.pedidos.repository.ItemPedidoRepository;
import br.edu.tcc.pedidos.repository.PedidoRepository;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PedidoService {

    private final PedidoRepository pedidoRepository;
    private final ItemPedidoRepository itemPedidoRepository;
    private final EmpresaService empresaService;
    private final ClienteService clienteService;
    private final ApplicationEventPublisher eventPublisher;

    public PedidoService(
            PedidoRepository pedidoRepository,
            ItemPedidoRepository itemPedidoRepository,
            EmpresaService empresaService,
            ClienteService clienteService,
            ApplicationEventPublisher eventPublisher) {
        this.pedidoRepository = pedidoRepository;
        this.itemPedidoRepository = itemPedidoRepository;
        this.empresaService = empresaService;
        this.clienteService = clienteService;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Pedido criarPedido(long tenantId, long clienteId, List<ItemPedido> itens) {
        empresaService.validarEmpresa(tenantId);
        Cliente cliente = clienteService.buscarNaEmpresa(tenantId, clienteId);
        BigDecimal total = calcularTotal(itens);
        Pedido pedido = pedidoRepository.save(new Pedido(tenantId, cliente, total));

        itens.forEach(item -> item.vincularAoPedido(pedido));
        itemPedidoRepository.saveAll(itens);
        publicarAlteracaoPedidos(tenantId);
        return pedido;
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public Page<PedidoResumo> listar(long tenantId, Pageable pageable) {
        empresaService.validarEmpresa(tenantId);
        return pedidoRepository.listarDaEmpresa(tenantId, pageable);
    }

    @Transactional
    public Pedido alterarStatus(long tenantId, long pedidoId, StatusPedido status) {
        Pedido pedido = pedidoRepository.buscarDaEmpresa(tenantId, pedidoId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Pedido não encontrado nesta empresa"));
        pedido.alterarStatus(status);
        pedidoRepository.save(pedido);
        publicarAlteracaoPedidos(tenantId);
        return pedido;
    }

    private BigDecimal calcularTotal(List<ItemPedido> itens) {
        return itens.stream()
                .map(item -> item.getPrecoUnitario().multiply(BigDecimal.valueOf(item.getQuantidade())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    private void publicarAlteracaoPedidos(long tenantId) {
        eventPublisher.publishEvent(new PedidosAlterados(tenantId));
    }
}
