package br.edu.tcc.pedidos.model;

import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record PedidoResumo(
        long id,
        long clienteId,
        String clienteNome,
        StatusPedido status,
        BigDecimal total,
        OffsetDateTime criadoEm) {
}
