package br.edu.tcc.pedidos.exception;

public class CapacidadeBancoExcedidaException extends RuntimeException {

    public CapacidadeBancoExcedidaException() {
        super("O limite de operações simultâneas no banco foi atingido");
    }
}
