package br.edu.tcc.pedidos.dto.request;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record NovoItemRequest(
        @NotBlank @Size(max = 200) String descricao,
        @NotNull @Min(1) @Max(1_000_000) Integer quantidade,
        @NotNull @DecimalMin("0.00") @Digits(integer = 10, fraction = 2) BigDecimal precoUnitario) {
}
