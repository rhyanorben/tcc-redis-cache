# TCC — PostgreSQL e Redis

Experimento de Engenharia de Computação que compara a mesma aplicação com PostgreSQL e com cache-aside Redis. Uma instância atende várias empresas; a operação avaliada é a **listagem paginada de pedidos de uma empresa**.

## Estado atual

- API implementada com empresa, cliente, pedido e item_pedido.
- Cache opcional, desligado por padrão; 39 testes automatizados validados localmente.
- PostgreSQL e Redis implantados anteriormente nas VMs de dados.
- API, migrações, usuários da aplicação e ACL Redis pendentes de implantação.
- Geração de carga com k6 e campanha experimental pendentes.

| VM | IP | Função |
| --- | --- | --- |
| tcc-app | 10.10.10.10 | API; possui apenas os clientes PostgreSQL/Redis instalados |
| tcc-postgres | 10.10.10.20 | PostgreSQL |
| tcc-redis | 10.10.10.30 | Redis |

O estado das VMs vem do [registro de 15/10/2026](infra/DEPLOYMENT.md). Alterar arquivos locais não implanta serviços; qualquer alteração nas VMs depende de confirmação.

## Desenvolvimento

Abra `app/pom.xml` no IntelliJ como projeto Maven e selecione Java 21. Para compilar e testar, na raiz do repositório, tenha Java 21, Maven 3.6.3+, Python 3 e Docker acessível:

```sh
mvn -f app/pom.xml verify
```

Os testes usam PostgreSQL e Redis descartáveis locais, sem acessar as VMs. Não versione `.env`, `secrets/`, resultados de build ou configurações locais da IDE.

## Onde encontrar

| Conteúdo | Local |
| --- | --- |
| Modelo, API e geração de dados | [docs/IMPLEMENTACAO.md](docs/IMPLEMENTACAO.md) |
| Cache: configuração e consistência | [docs/CACHE.md](docs/CACHE.md) |
| Aplicação e exemplos HTTP | [app/README.md](app/README.md) |
| Migrações | [database/README.md](database/README.md) |
| PostgreSQL, Redis e rede | [infra/README.md](infra/README.md) |
| Implantação da API | [infra/app/README.md](infra/app/README.md) |
| Versões | [VERSIONS.md](VERSIONS.md) |

`scripts/` contém o gerador de dados. `load/` e `monitoring/` estão reservados para as próximas etapas; `results/` guarda resultados locais ignorados pelo Git.
