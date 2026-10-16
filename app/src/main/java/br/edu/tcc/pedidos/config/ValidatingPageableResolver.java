package br.edu.tcc.pedidos.config;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.apache.commons.lang3.ObjectUtils;
import org.springframework.core.MethodParameter;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;

public class ValidatingPageableResolver implements HandlerMethodArgumentResolver {

    private static final Set<String> CAMPOS_ORDENAVEIS = Set.of("criadoEm", "id", "status", "total");
    private static final Sort ORDENACAO_PADRAO = Sort.by(Sort.Direction.DESC, "criadoEm", "id");

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.getParameterType().equals(Pageable.class);
    }

    @Override
    public Pageable resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer container,
            NativeWebRequest request,
            WebDataBinderFactory binderFactory) {
        int pagina = lerInteiro(request.getParameter("page"), 0, 0, 1_000_000);
        int tamanho = lerInteiro(request.getParameter("size"), 20, 1, 100);
        Sort ordenacao = lerOrdenacao(request.getParameterValues("sort"));
        return PageRequest.of(pagina, tamanho, ordenacao);
    }

    private int lerInteiro(String valor, int padrao, int minimo, int maximo) {
        if (ObjectUtils.isEmpty(valor)) {
            return padrao;
        }

        try {
            int numero = Integer.parseInt(valor);
            if (numero < minimo || numero > maximo) {
                throw parametroInvalido();
            }
            return numero;
        } catch (NumberFormatException exception) {
            throw parametroInvalido();
        }
    }

    private Sort lerOrdenacao(String[] parametros) {
        if (ObjectUtils.isEmpty(parametros)) {
            return ORDENACAO_PADRAO;
        }

        List<Sort.Order> criterios = new ArrayList<>();
        for (String parametro : parametros) {
            String[] partes = parametro.split(",", -1);
            if (partes.length > 2 || !CAMPOS_ORDENAVEIS.contains(partes[0])) {
                throw parametroInvalido();
            }

            Sort.Direction direcao = partes.length == 2 ? lerDirecao(partes[1]) : Sort.Direction.ASC;
            criterios.add(new Sort.Order(direcao, partes[0]));
        }

        Sort ordenacao = Sort.by(criterios);
        if (ObjectUtils.isEmpty(ordenacao.getOrderFor("id"))) {
            ordenacao = ordenacao.and(Sort.by(Sort.Direction.DESC, "id"));
        }
        return ordenacao;
    }

    private Sort.Direction lerDirecao(String direcao) {
        try {
            return Sort.Direction.fromString(direcao);
        } catch (IllegalArgumentException exception) {
            throw parametroInvalido();
        }
    }

    private ResponseStatusException parametroInvalido() {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, "Paginação ou ordenação inválida");
    }
}
