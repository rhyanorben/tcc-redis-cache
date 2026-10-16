package br.edu.tcc.pedidos.controller;

import br.edu.tcc.pedidos.dto.request.NovaEmpresaRequest;
import br.edu.tcc.pedidos.dto.response.EmpresaResponse;
import br.edu.tcc.pedidos.mapper.EmpresaMapper;
import br.edu.tcc.pedidos.model.Empresa;
import br.edu.tcc.pedidos.service.EmpresaService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/empresas")
public class EmpresaController {

    private final EmpresaService empresaService;
    private final EmpresaMapper empresaMapper;

    public EmpresaController(EmpresaService empresaService, EmpresaMapper empresaMapper) {
        this.empresaService = empresaService;
        this.empresaMapper = empresaMapper;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public EmpresaResponse criarEmpresa(@Valid @RequestBody NovaEmpresaRequest novaEmpresa) {
        Empresa empresa = empresaService.criarEmpresa(novaEmpresa.nome());
        return empresaMapper.paraResponse(empresa);
    }
}
