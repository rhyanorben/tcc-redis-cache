package br.edu.tcc.pedidos.mapper;

import br.edu.tcc.pedidos.dto.response.ClienteResponse;
import br.edu.tcc.pedidos.model.Cliente;
import org.springframework.stereotype.Component;

@Component
public class ClienteMapper {

    public ClienteResponse paraResponse(Cliente cliente) {
        return new ClienteResponse(cliente.getId(), cliente.getTenantId(), cliente.getNome());
    }
}
