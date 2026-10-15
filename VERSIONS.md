# Versões do ambiente experimental

Atualizado em 15/10/2026 a partir do código e do registro da implantação. Valores observados nas VMs referem-se à preparação anterior; esta sincronização não verificou novamente nem alterou as VMs.

| Tecnologia | Versão / estado |
| --- | --- |
| Ubuntu Server | 24.04.5 LTS, registrado nas VMs. |
| Java | Alvo Java 21; testes locais anteriores com Temurin 21.0.9. Runtime da VM app pendente. |
| Spring Boot | 3.5.16, fixado em `app/pom.xml`. |
| PostgreSQL | 17.11, imagem fixada por digest no exemplo de ambiente. |
| Redis | 7.4.11, imagem fixada por digest no exemplo de ambiente. |
| Docker Engine | 29.9.1 nas VMs de PostgreSQL e Redis. |
| Docker Compose | 5.6.0 nas VMs de PostgreSQL e Redis. |
| k6 | A DEFINIR — ainda não implementado. |
| KVM/QEMU | A REGISTRAR antes dos experimentos. |
| libvirt | A REGISTRAR antes dos experimentos. |

## Imagens dos serviços de dados

```text
postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85
```

O Dockerfile da aplicação usa `maven:3.9.9-eclipse-temurin-21` no build e `eclipse-temurin:21-jre-jammy` na execução. Essas bases ainda usam tags e devem ter seus digests registrados antes dos ensaios. A imagem Docker da aplicação ainda não foi construída ou implantada.

Para a campanha experimental, registrar também versão exata do JDK/JRE em execução, recursos de cada VM, commit Git, digest da imagem final da aplicação, volume de dados, configuração de paginação, pool de conexões e parâmetros de cache.
