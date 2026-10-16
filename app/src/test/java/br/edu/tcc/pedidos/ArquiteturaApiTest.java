package br.edu.tcc.pedidos;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.Entity;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Parameter;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

class ArquiteturaApiTest {

    private static final String PACOTE_BASE = "br.edu.tcc.pedidos";
    private static final String PACOTE_MODELO = PACOTE_BASE + ".model";
    private static final String PACOTE_REQUEST = PACOTE_BASE + ".dto.request";
    private static final String PACOTE_RESPONSE = PACOTE_BASE + ".dto.response";

    @Test
    void controllersExpoemApenasDtosNosCorposDasRequisicoesERespostas() throws ClassNotFoundException {
        List<Class<?>> controllers = buscarControllers();

        assertThat(controllers).isNotEmpty();

        for (Class<?> controller : controllers) {
            List<Method> endpoints = List.of(controller.getDeclaredMethods()).stream()
                    .filter(metodo -> AnnotatedElementUtils.hasAnnotation(metodo, RequestMapping.class))
                    .toList();

            assertThat(endpoints).as("Rotas de %s", controller.getSimpleName()).isNotEmpty();

            for (Method endpoint : endpoints) {
                assertThat(endpoint.getReturnType().getPackageName())
                        .as("Resposta de %s.%s", controller.getSimpleName(), endpoint.getName())
                        .isEqualTo(PACOTE_RESPONSE);

                for (Parameter parametro : endpoint.getParameters()) {
                    if (parametro.isAnnotationPresent(RequestBody.class)) {
                        assertThat(parametro.getType().getPackageName())
                                .as("Corpo de %s.%s", controller.getSimpleName(), endpoint.getName())
                                .isEqualTo(PACOTE_REQUEST);
                    }
                }
            }
        }
    }

    @Test
    void dtosNaoEncadeiamEntidadesNosCamposOuNasColecoes() throws ClassNotFoundException {
        List<Class<?>> dtos = buscarClasses(PACOTE_BASE + ".dto");

        assertThat(dtos).isNotEmpty();

        for (Class<?> dto : dtos) {
            for (Field campo : dto.getDeclaredFields()) {
                if (!Modifier.isStatic(campo.getModifiers())) {
                    exigirContratoSemEntidade(campo.getGenericType(), dto.getSimpleName() + "." + campo.getName());
                }
            }
        }
    }

    @Test
    void entidadesSaoTiposPublicosIndependentesNoPacoteModel() throws ClassNotFoundException {
        for (String nome : List.of("Empresa", "Cliente", "Pedido", "ItemPedido")) {
            Class<?> entidade = Class.forName(PACOTE_MODELO + "." + nome);

            assertThat(entidade.getEnclosingClass()).as("Entidade %s", nome).isNull();
            assertThat(Modifier.isPublic(entidade.getModifiers())).as("Visibilidade de %s", nome).isTrue();
            assertThat(entidade.getPackageName()).isEqualTo(PACOTE_MODELO);
            assertThat(entidade.isAnnotationPresent(Entity.class)).as("Entidade JPA %s", nome).isTrue();

            for (Field campo : entidade.getDeclaredFields()) {
                assertThat(campo.getType().getPackageName())
                        .as("Dependência de %s.%s", nome, campo.getName())
                        .doesNotStartWith(PACOTE_BASE + ".dto");
            }
        }
    }

    @Test
    void repositoriosUsamContratoJpaParaAsQuatroEntidades() throws ClassNotFoundException {
        for (String nome : List.of("Empresa", "Cliente", "Pedido", "ItemPedido")) {
            Class<?> repositorio = Class.forName(PACOTE_BASE + ".repository." + nome + "Repository");

            assertThat(repositorio.isInterface()).as("Repositório de %s", nome).isTrue();
            assertThat(JpaRepository.class.isAssignableFrom(repositorio)).as("Contrato JPA de %s", nome).isTrue();
        }
    }

    @Test
    void servicosECacheNaoDependemDeDtosOuMappersHttp() throws ClassNotFoundException {
        List<Class<?>> classes = new ArrayList<>(buscarClasses(PACOTE_BASE + ".service"));
        classes.addAll(buscarClasses(PACOTE_BASE + ".cache"));

        assertThat(classes).isNotEmpty();

        for (Class<?> classe : classes) {
            for (Field campo : classe.getDeclaredFields()) {
                exigirTipoSemCamadaHttp(campo.getGenericType(), classe.getSimpleName() + "." + campo.getName());
            }
            for (Constructor<?> construtor : classe.getDeclaredConstructors()) {
                for (Type parametro : construtor.getGenericParameterTypes()) {
                    exigirTipoSemCamadaHttp(parametro, classe.getSimpleName());
                }
            }
            for (Method metodo : classe.getDeclaredMethods()) {
                exigirTipoSemCamadaHttp(metodo.getGenericReturnType(), classe.getSimpleName() + "." + metodo.getName());
                for (Type parametro : metodo.getGenericParameterTypes()) {
                    exigirTipoSemCamadaHttp(parametro, classe.getSimpleName() + "." + metodo.getName());
                }
            }
        }
    }

    @Test
    void tenantIdEDeclaradoComoCabecalhoSemNomeExplicito() throws ClassNotFoundException {
        int cabecalhosEncontrados = 0;

        for (Class<?> controller : buscarControllers()) {
            for (Method metodo : controller.getDeclaredMethods()) {
                for (Parameter parametro : metodo.getParameters()) {
                    if (parametro.isAnnotationPresent(RequestHeader.class)) {
                        RequestHeader cabecalho = parametro.getAnnotation(RequestHeader.class);

                        assertThat(parametro.getName()).isEqualTo("tenantId");
                        assertThat(parametro.getType()).isEqualTo(long.class);
                        assertThat(cabecalho.name()).isEmpty();
                        assertThat(cabecalho.value()).isEmpty();
                        cabecalhosEncontrados++;
                    }
                }
            }
        }

        assertThat(cabecalhosEncontrados).isPositive();
    }

    private List<Class<?>> buscarControllers() throws ClassNotFoundException {
        return buscarClasses(PACOTE_BASE + ".controller").stream()
                .filter(classe -> AnnotatedElementUtils.hasAnnotation(classe, RestController.class))
                .toList();
    }

    private List<Class<?>> buscarClasses(String pacote) throws ClassNotFoundException {
        ClassPathScanningCandidateComponentProvider scanner = new ClassPathScanningCandidateComponentProvider(false);
        scanner.addIncludeFilter((metadados, fabricaMetadados) -> true);
        List<Class<?>> classes = new ArrayList<>();

        for (BeanDefinition definicao : scanner.findCandidateComponents(pacote)) {
            classes.add(Class.forName(definicao.getBeanClassName()));
        }

        return classes;
    }

    private void exigirContratoSemEntidade(Type tipo, String campo) {
        if (tipo instanceof Class<?> classe) {
            assertThat(classe.getPackageName().equals(PACOTE_MODELO) && !classe.isEnum())
                    .as("Campo %s não deve expor a entidade %s", campo, classe.getSimpleName())
                    .isFalse();
        } else if (tipo instanceof ParameterizedType tipoGenerico) {
            for (Type argumento : tipoGenerico.getActualTypeArguments()) {
                exigirContratoSemEntidade(argumento, campo);
            }
        }
    }

    private void exigirTipoSemCamadaHttp(Type tipo, String origem) {
        if (tipo instanceof Class<?> classe) {
            assertThat(classe.getPackageName())
                    .as("Dependência de %s", origem)
                    .doesNotStartWith(PACOTE_BASE + ".dto")
                    .doesNotStartWith(PACOTE_BASE + ".mapper");
        } else if (tipo instanceof ParameterizedType tipoGenerico) {
            for (Type argumento : tipoGenerico.getActualTypeArguments()) {
                exigirTipoSemCamadaHttp(argumento, origem);
            }
        }
    }
}
