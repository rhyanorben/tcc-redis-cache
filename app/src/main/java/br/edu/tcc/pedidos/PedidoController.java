package br.edu.tcc.pedidos;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import static br.edu.tcc.pedidos.Contratos.*;

@RestController
@RequestMapping("/api")
@Validated
public class PedidoController {
    private final PedidoService service;
    public PedidoController(PedidoService service) { this.service = service; }

    @PostMapping("/empresas") @ResponseStatus(HttpStatus.CREATED)
    public Empresa criarEmpresa(@Valid @RequestBody NovaEmpresa request) { return service.criarEmpresa(request); }

    @PostMapping("/clientes") @ResponseStatus(HttpStatus.CREATED)
    public Cliente criarCliente(@RequestHeader("X-Tenant-Id") @Positive long tenant,
                                 @Valid @RequestBody NovoCliente request) {
        return service.criarCliente(tenant, request);
    }
    @PostMapping("/pedidos") @ResponseStatus(HttpStatus.CREATED)
    public PedidoResumo criarPedido(@RequestHeader("X-Tenant-Id") @Positive long tenant,
                                      @Valid @RequestBody NovoPedido request) {
        return service.criarPedido(tenant, request);
    }
    @GetMapping("/pedidos")
    public PaginaPedidos listar(@RequestHeader("X-Tenant-Id") @Positive long tenant,
                                  @RequestParam(defaultValue = "0") @Min(0) @Max(1_000_000) int page,
                                  @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return service.listar(tenant, page, size);
    }
    @PatchMapping("/pedidos/{id}/status")
    public PedidoResumo alterarStatus(@RequestHeader("X-Tenant-Id") @Positive long tenant,
                                        @PathVariable @Positive long id,
                                        @Valid @RequestBody AlterarStatus request) {
        return service.alterarStatus(tenant, id, request);
    }
}
