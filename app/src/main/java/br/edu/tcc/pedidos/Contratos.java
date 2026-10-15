package br.edu.tcc.pedidos;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;

public final class Contratos {
    private Contratos() {}
    public enum Status { ABERTO, CONFIRMADO, CANCELADO }
    public record NovaEmpresa(@NotBlank @Size(max = 160) String nome) {}
    public record NovoCliente(@NotBlank @Size(max = 160) String nome) {}
    public record NovoItem(
            @NotBlank @Size(max = 200) String descricao,
            @NotNull @Min(1) @Max(1_000_000) Integer quantidade,
            @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2) BigDecimal precoUnitario) {}
    public record NovoPedido(
            @NotNull @Positive Long clienteId,
            @NotEmpty @Size(max = 100) List<@NotNull @Valid NovoItem> itens) {}
    public record AlterarStatus(@NotNull Status status) {}
    public record Empresa(long id, String nome) {}
    public record Cliente(long id, long tenantId, String nome) {}
    public record PedidoResumo(long id, long clienteId, String clienteNome,
                                Status status, BigDecimal total, OffsetDateTime criadoEm) {}
    public record PaginaPedidos(List<PedidoResumo> content, int page, int size,
                                 long totalElements, long totalPages, boolean first, boolean last) {
        static PaginaPedidos of(List<PedidoResumo> content, int page, int size, long total) {
            long pages = total / size + (total % size == 0 ? 0 : 1);
            return new PaginaPedidos(List.copyOf(content), page, size, total, pages,
                    page == 0, (long) page + 1 >= pages);
        }
    }
}
