package br.edu.tcc.pedidos.service;

import br.edu.tcc.pedidos.model.Cliente;
import br.edu.tcc.pedidos.repository.ClienteRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ClienteService {

    private final ClienteRepository clienteRepository;
    private final EmpresaService empresaService;

    public ClienteService(ClienteRepository clienteRepository, EmpresaService empresaService) {
        this.clienteRepository = clienteRepository;
        this.empresaService = empresaService;
    }

    @Transactional
    public Cliente criarCliente(long tenantId, String nome) {
        empresaService.validarEmpresa(tenantId);
        return clienteRepository.save(new Cliente(tenantId, nome.trim()));
    }

    @Transactional(readOnly = true)
    public Cliente buscarNaEmpresa(long tenantId, long clienteId) {
        return clienteRepository.buscarDaEmpresa(tenantId, clienteId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Cliente não encontrado nesta empresa"));
    }
}
