package br.edu.tcc.pedidos;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;

public final class Contratos {

    private Contratos() {
    }

    public enum Status {
        ABERTO,
        CONFIRMADO,
        CANCELADO
    }

    public record NovaEmpresa(@NotBlank @Size(max = 160) String nome) {
    }

    public record NovoCliente(@NotBlank @Size(max = 160) String nome) {
    }

    public record NovoItem(
            @NotBlank @Size(max = 200) String descricao,
            @NotNull @Min(1) @Max(1_000_000) Integer quantidade,
            @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2) BigDecimal precoUnitario) {
    }

    public record NovoPedido(
            @NotNull @Positive Long clienteId,
            @NotEmpty @Size(max = 100) List<@NotNull @Valid NovoItem> itens) {
    }

    public record AlterarStatus(@NotNull Status status) {
    }

    public record Empresa(long id, String nome) {
    }

    public record Cliente(long id, long tenantId, String nome) {
    }

    public record PedidoResumo(
            long id,
            long clienteId,
            String clienteNome,
            Status status,
            BigDecimal total,
            OffsetDateTime criadoEm) {
    }

    public record PaginaPedidos(
            List<PedidoResumo> content,
            int page,
            int size,
            long totalElements,
            long totalPages,
            boolean first,
            boolean last) {

        static PaginaPedidos of(List<PedidoResumo> pedidos, int pagina, int tamanho, long totalPedidos) {
            long totalPaginas = totalPedidos / tamanho + (totalPedidos % tamanho == 0 ? 0 : 1);
            boolean primeiraPagina = pagina == 0;
            boolean ultimaPagina = (long) pagina + 1 >= totalPaginas;

            return new PaginaPedidos(
                    List.copyOf(pedidos),
                    pagina,
                    tamanho,
                    totalPedidos,
                    totalPaginas,
                    primeiraPagina,
                    ultimaPagina);
        }
    }
}
