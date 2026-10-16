package br.edu.tcc.pedidos.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NovoClienteRequest(@NotBlank @Size(max = 160) String nome) {
}
