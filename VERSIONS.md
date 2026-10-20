# Versões e artefatos

Referência das VMs atualizada em 16/10/2026. Diferencie versões confirmadas, ferramentas locais e implantação pendente.

| Tecnologia | Versão e situação |
| --- | --- |
| Ubuntu Server nas VMs de serviço | 24.04.5 LTS, registrado na preparação |
| Java | Alvo 21; testes locais anteriores com Temurin 21.0.9; JRE final da VM pendente |
| Spring Boot | 3.5.16 em `app/pom.xml` |
| PostgreSQL | 17.11, confirmado em 16/10/2026 |
| `pg_stat_statements` | 1.11, habilitado em 16/10/2026 |
| Redis | 7.4.11, confirmado em 16/10/2026 |
| Docker Engine nas VMs de dados | 29.9.1 |
| Docker Compose nas VMs de dados | 5.6.0 |
| k6 | 1.6.0; imagem disponível localmente, instalação no Host 2 pendente |
| KVM/QEMU e libvirt | Registrar versões efetivas antes da campanha |

Imagens fixadas:

```text
postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85
grafana/k6@sha256:be2a9ceb1b6ffc573277af4157135882a6d6433968b41e858ab02c5fd5847532
```

O Dockerfile usa `maven:3.9.9-eclipse-temurin-21` e `eclipse-temurin:21-jre-jammy`. O build da imagem final da API e seu runtime na VM estão pendentes; registre o digest final antes de iniciar a campanha. Spring Data Redis/Lettuce seguem as versões gerenciadas pelo Spring Boot.

Recursos confirmados em 16/10/2026: aplicação e PostgreSQL com 2 vCPU/4 GiB cada; Redis com 1 vCPU/2 GiB e `maxmemory=1gb`. A VM de carga no segundo computador ainda precisa ser preparada e verificada.

Antes dos ensaios, registre commit, digests, JRE, recursos, base e índices, paginação, empresas ativas, ritmo da carga, pool, namespace, TTL e timeout. Use os mesmos artefatos nos dois cenários e siga [EXPERIMENTO.md](docs/EXPERIMENTO.md). Nenhum resultado de desempenho é estabelecido por esse registro.
