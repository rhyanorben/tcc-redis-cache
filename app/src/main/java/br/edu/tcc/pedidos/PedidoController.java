package br.edu.tcc.pedidos;

import br.edu.tcc.pedidos.Contratos.AlterarStatus;
import br.edu.tcc.pedidos.Contratos.Cliente;
import br.edu.tcc.pedidos.Contratos.Empresa;
import br.edu.tcc.pedidos.Contratos.NovaEmpresa;
import br.edu.tcc.pedidos.Contratos.NovoCliente;
import br.edu.tcc.pedidos.Contratos.NovoPedido;
import br.edu.tcc.pedidos.Contratos.PaginaPedidos;
import br.edu.tcc.pedidos.Contratos.PedidoResumo;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@Validated
public class PedidoController {

    private final PedidoService pedidoService;
    private final ConsultaPedidosService consultaPedidosService;

    public PedidoController(PedidoService pedidoService, ConsultaPedidosService consultaPedidosService) {
        this.pedidoService = pedidoService;
        this.consultaPedidosService = consultaPedidosService;
    }

    @PostMapping("/empresas")
    @ResponseStatus(HttpStatus.CREATED)
    public Empresa criarEmpresa(@Valid @RequestBody NovaEmpresa novaEmpresa) {
        return pedidoService.criarEmpresa(novaEmpresa);
    }

    @PostMapping("/clientes")
    @ResponseStatus(HttpStatus.CREATED)
    public Cliente criarCliente(
            @RequestHeader("X-Tenant-Id") @Positive long tenantId,
            @Valid @RequestBody NovoCliente novoCliente) {
        return pedidoService.criarCliente(tenantId, novoCliente);
    }

    @PostMapping("/pedidos")
    @ResponseStatus(HttpStatus.CREATED)
    public PedidoResumo criarPedido(
            @RequestHeader("X-Tenant-Id") @Positive long tenantId,
            @Valid @RequestBody NovoPedido novoPedido) {
        return pedidoService.criarPedido(tenantId, novoPedido);
    }

    @GetMapping("/pedidos")
    public PaginaPedidos listar(
            @RequestHeader("X-Tenant-Id") @Positive long tenantId,
            @RequestParam(name = "page", defaultValue = "0") @Min(0) @Max(1_000_000) int pagina,
            @RequestParam(name = "size", defaultValue = "20") @Min(1) @Max(100) int tamanho) {
        return consultaPedidosService.listar(tenantId, pagina, tamanho);
    }

    @PatchMapping("/pedidos/{id}/status")
    public PedidoResumo alterarStatus(
            @RequestHeader("X-Tenant-Id") @Positive long tenantId,
            @PathVariable("id") @Positive long pedidoId,
            @Valid @RequestBody AlterarStatus alteracao) {
        return pedidoService.alterarStatus(tenantId, pedidoId, alteracao);
    }
}
