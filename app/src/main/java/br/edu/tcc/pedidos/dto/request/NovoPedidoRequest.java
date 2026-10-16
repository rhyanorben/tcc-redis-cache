package br.edu.tcc.pedidos.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record NovoPedidoRequest(
        @NotNull @Positive Long clienteId,
        @NotEmpty @Size(max = 100) List<@NotNull @Valid NovoItemRequest> itens) {
}
