package br.edu.tcc.pedidos.mapper;

import br.edu.tcc.pedidos.dto.request.NovoItemRequest;
import br.edu.tcc.pedidos.model.ItemPedido;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class ItemPedidoMapper {

    public List<ItemPedido> paraNovosItens(List<NovoItemRequest> itens) {
        return itens.stream()
                .map(this::paraNovoItem)
                .toList();
    }

    private ItemPedido paraNovoItem(NovoItemRequest item) {
        return new ItemPedido(item.descricao().trim(), item.quantidade(), item.precoUnitario());
    }
}
