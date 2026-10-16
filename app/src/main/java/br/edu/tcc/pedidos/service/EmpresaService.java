package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.model.Empresa;
import br.edu.tcc.pedidos.repository.EmpresaRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class EmpresaService {

    private final EmpresaRepository empresaRepository;

    public EmpresaService(EmpresaRepository empresaRepository) {
        this.empresaRepository = empresaRepository;
    }

    @Transactional
    public Empresa criarEmpresa(String nome) {
        return empresaRepository.save(new Empresa(nome.trim()));
    }

    @Transactional(readOnly = true)
    public void validarEmpresa(long empresaId) {
        if (!empresaRepository.existsById(empresaId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Empresa não encontrada");
        }
    }
}
