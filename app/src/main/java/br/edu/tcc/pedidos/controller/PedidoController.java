package br.edu.tcc.pedidos.controller;

import br.edu.tcc.pedidos.dto.request.AlterarStatusRequest;
import br.edu.tcc.pedidos.dto.request.NovoPedidoRequest;
import br.edu.tcc.pedidos.dto.response.PaginaPedidosResponse;
import br.edu.tcc.pedidos.dto.response.PedidoResumoResponse;
import br.edu.tcc.pedidos.mapper.ItemPedidoMapper;
import br.edu.tcc.pedidos.mapper.PedidoMapper;
import br.edu.tcc.pedidos.model.ItemPedido;
import br.edu.tcc.pedidos.model.Pedido;
import br.edu.tcc.pedidos.model.PedidoResumo;
import br.edu.tcc.pedidos.service.ConsultaPedidosService;
import br.edu.tcc.pedidos.service.PedidoService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/pedidos")
@Validated
public class PedidoController {

    private final PedidoService pedidoService;
    private final ConsultaPedidosService consultaPedidosService;
    private final PedidoMapper pedidoMapper;
    private final ItemPedidoMapper itemPedidoMapper;

    public PedidoController(
            PedidoService pedidoService,
            ConsultaPedidosService consultaPedidosService,
            PedidoMapper pedidoMapper,
            ItemPedidoMapper itemPedidoMapper) {
        this.pedidoService = pedidoService;
        this.consultaPedidosService = consultaPedidosService;
        this.pedidoMapper = pedidoMapper;
        this.itemPedidoMapper = itemPedidoMapper;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public PedidoResumoResponse criarPedido(
            @RequestHeader @Positive long tenantId,
            @Valid @RequestBody NovoPedidoRequest novoPedido) {
        List<ItemPedido> itens = itemPedidoMapper.paraNovosItens(novoPedido.itens());
        Pedido pedido = pedidoService.criarPedido(tenantId, novoPedido.clienteId(), itens);
        return pedidoMapper.paraResumoResponse(pedido);
    }

    @GetMapping
    public PaginaPedidosResponse listar(@RequestHeader @Positive long tenantId, Pageable pageable) {
        Page<PedidoResumo> pedidos = consultaPedidosService.listar(tenantId, pageable);
        return pedidoMapper.paraPaginaResponse(pedidos);
    }

    @PatchMapping("/{id}/status")
    public PedidoResumoResponse alterarStatus(
            @RequestHeader @Positive long tenantId,
            @PathVariable("id") @Positive long pedidoId,
            @Valid @RequestBody AlterarStatusRequest alteracao) {
        Pedido pedido = pedidoService.alterarStatus(tenantId, pedidoId, alteracao.status());
        return pedidoMapper.paraResumoResponse(pedido);
    }
}
