package br.edu.tcc.pedidos.controller;

import br.edu.tcc.pedidos.dto.request.NovoClienteRequest;
import br.edu.tcc.pedidos.dto.response.ClienteResponse;
import br.edu.tcc.pedidos.mapper.ClienteMapper;
import br.edu.tcc.pedidos.model.Cliente;
import br.edu.tcc.pedidos.service.ClienteService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/clientes")
@Validated
public class ClienteController {

    private final ClienteService clienteService;
    private final ClienteMapper clienteMapper;

    public ClienteController(ClienteService clienteService, ClienteMapper clienteMapper) {
        this.clienteService = clienteService;
        this.clienteMapper = clienteMapper;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ClienteResponse criarCliente(
            @RequestHeader @Positive long tenantId,
            @Valid @RequestBody NovoClienteRequest novoCliente) {
        Cliente cliente = clienteService.criarCliente(tenantId, novoCliente.nome());
        return clienteMapper.paraResponse(cliente);
    }
}
