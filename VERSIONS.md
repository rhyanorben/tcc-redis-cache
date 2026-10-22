# Versões e artefatos

Referência das VMs atualizada em 22/10/2026. O registro distingue o ambiente do piloto e a campanha completa ainda pendente.

| Tecnologia | Versão e situação |
| --- | --- |
| Ubuntu Server nas VMs de serviço | 24.04.5 LTS, registrado na preparação |
| Java | Alvo 21; imagem implantada com Temurin 21.0.12.1+1; testes locais anteriores com Temurin 21.0.9 |
| Spring Boot | 3.5.16 em `app/pom.xml` |
| PostgreSQL | 17.11, confirmado novamente em 20/10/2026 |
| `pg_stat_statements` | 1.11, habilitado em 16/10/2026 |
| Redis | 7.4.11, confirmado novamente em 20/10/2026 |
| Docker Engine nas quatro VMs | 29.9.1 |
| Docker Compose nas quatro VMs | 5.6.0 |
| containerd / Buildx na tcc-app e tcc-load | 2.4.2 / 0.38.0 |
| k6 — executor e piloto | 1.6.0 em contêiner, digest fixado abaixo; confirmado na tcc-load em 22/10 |
| k6 — binário nativo da tcc-load | 2.3.0; permanece instalado, mas o executor usa o contêiner 1.6.0 |
| Ethernet do computador 1 | `r8169` do kernel `7.0.0-38-generic`; substituiu o `r8168` 8.052.01 nessa placa |
| driverctl no computador 1 | 0.115-1; escolha persistente de `r8169` somente no PCI `0000:04:00.0` |
| KVM/QEMU e libvirt no computador 1 | QEMU 8.2.2 e libvirt 10.0.0, confirmados em 22/10/2026 |

Imagens fixadas:

```text
postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85
grafana/k6@sha256:be2a9ceb1b6ffc573277af4157135882a6d6433968b41e858ab02c5fd5847532
```

O digest k6 acima é usado pelo executor na tcc-load. O comando `k6 version` fora do contêiner consulta outro binário; para reproduzir o piloto, use o executor com a imagem fixada.

O Dockerfile usa `maven:3.9.9-eclipse-temurin-21` e `eclipse-temurin:21-jre-jammy`. A imagem `tcc-pedidos:0.1.0`, construída a partir do código da API no commit `b1112e254d41fc3f15a41aff67b19a68ba922ddc`, foi usada nos dois modos de validação. Seu ID local é:

```text
sha256:55f2b25ac4de19ceb22aa867ce78b17e3266a707d2ad676d42c534610831c35b
```

Esse ID identifica o artefato local; não é um digest de distribuição em registro. As tags das imagens base permanecem mutáveis: registre seus digests antes da campanha. Spring Data Redis/Lettuce seguem as versões gerenciadas pelo Spring Boot.

Recursos confirmados em 16/10/2026: aplicação e PostgreSQL com 2 vCPU/4 GiB cada; Redis com 1 vCPU/2 GiB e `maxmemory=1gb`. A tcc-load possui 4 vCPU e 4 GiB; Docker e a imagem k6 de referência foram preparados em 22/10. Os três coletores de serviço foram conferidos com dados reais. Veja [ETHERNET.md](infra/network/ETHERNET.md).

Antes dos ensaios, registre commit, digests, JRE, recursos, base e índices, paginação, empresas ativas, ritmo da carga, pool, namespace, TTL e timeout. Use os mesmos artefatos nos dois cenários e siga [EXPERIMENTO.md](docs/EXPERIMENTO.md). Nenhum resultado de desempenho é estabelecido por esse registro.
