package br.edu.tcc.pedidos.dto.response;

import br.edu.tcc.pedidos.model.StatusPedido;
import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record PedidoResumoResponse(
        long id,
        long clienteId,
        String clienteNome,
        StatusPedido status,
        BigDecimal total,
        OffsetDateTime criadoEm) {
}
