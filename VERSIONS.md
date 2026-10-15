# Versões

Referência de 15/10/2026. Valores das VMs vêm da implantação registrada; não representam uma nova verificação remota.

| Tecnologia | Versão |
| --- | --- |
| Ubuntu Server nas VMs | 24.04.5 LTS |
| Java | Alvo 21; testes anteriores com Temurin 21.0.9 |
| Spring Boot | 3.5.16 em `app/pom.xml` |
| PostgreSQL | 17.11 |
| Redis | 7.4.11 |
| Docker Engine nas VMs de dados | 29.9.1 |
| Docker Compose nas VMs de dados | 5.6.0 |
| k6, KVM/QEMU e libvirt | Pendentes de registro |

As imagens dos bancos estão fixadas por digest nos respectivos `.env.example`:

```text
postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85
```

O Dockerfile usa `maven:3.9.9-eclipse-temurin-21` e `eclipse-temurin:21-jre-jammy`. O build da imagem da API e seu runtime na VM estão pendentes. Spring Data Redis/Lettuce seguem as versões gerenciadas pelo Spring Boot.

Antes dos ensaios, registre commit, digests das bases e da API, JRE em execução, recursos das VMs, volume de dados, paginação, pool de conexões, namespace, TTL e timeout do cache. Use os mesmos artefatos nos dois cenários.
