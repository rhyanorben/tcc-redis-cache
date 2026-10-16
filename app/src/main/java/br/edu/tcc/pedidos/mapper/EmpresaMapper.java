package br.edu.tcc.pedidos.mapper;

import br.edu.tcc.pedidos.dto.response.EmpresaResponse;
import br.edu.tcc.pedidos.model.Empresa;
import org.springframework.stereotype.Component;

@Component
public class EmpresaMapper {

    public EmpresaResponse paraResponse(Empresa empresa) {
        return new EmpresaResponse(empresa.getId(), empresa.getNome());
    }
}
