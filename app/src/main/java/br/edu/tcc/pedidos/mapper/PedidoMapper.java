package br.edu.tcc.pedidos.mapper;

import br.edu.tcc.pedidos.dto.response.PaginaPedidosResponse;
import br.edu.tcc.pedidos.dto.response.PedidoResumoResponse;
import br.edu.tcc.pedidos.model.Pedido;
import br.edu.tcc.pedidos.model.PedidoResumo;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;

@Component
public class PedidoMapper {

    public PedidoResumoResponse paraResumoResponse(Pedido pedido) {
        return new PedidoResumoResponse(
                pedido.getId(),
                pedido.getCliente().getId(),
                pedido.getCliente().getNome(),
                pedido.getStatus(),
                pedido.getTotal(),
                pedido.getCriadoEm());
    }

    public PedidoResumoResponse paraResumoResponse(PedidoResumo resumo) {
        return new PedidoResumoResponse(
                resumo.id(),
                resumo.clienteId(),
                resumo.clienteNome(),
                resumo.status(),
                resumo.total(),
                resumo.criadoEm());
    }

    public PaginaPedidosResponse paraPaginaResponse(Page<PedidoResumo> pedidos) {
        List<PedidoResumoResponse> resumos = pedidos.getContent().stream()
                .map(this::paraResumoResponse)
                .toList();
        return PaginaPedidosResponse.of(resumos, pedidos.getNumber(), pedidos.getSize(), pedidos.getTotalElements());
    }
}
