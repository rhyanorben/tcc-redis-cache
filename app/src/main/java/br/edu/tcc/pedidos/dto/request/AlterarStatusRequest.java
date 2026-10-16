package br.edu.tcc.pedidos.dto.request;

import br.edu.tcc.pedidos.model.StatusPedido;
import jakarta.validation.constraints.NotNull;

public record AlterarStatusRequest(@NotNull StatusPedido status) {
}
