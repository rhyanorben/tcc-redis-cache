# Ambiente experimental — PostgreSQL e Redis

Repositório do ambiente experimental do TCC de Engenharia de Computação. O objetivo é comparar o desempenho da mesma aplicação SaaS em arquitetura Single Instance Multi-Tenant (SIMT), na qual uma única instância atende múltiplos tenants, em duas configurações:

1. PostgreSQL como único serviço de armazenamento de dados.
2. PostgreSQL com Redis como camada de cache.

Este é o repositório principal de desenvolvimento. A aplicação inicial sem cache está implementada e testada localmente. A operação avaliada é a listagem paginada de pedidos de uma empresa. Entidades: empresa, cliente, pedido e item_pedido.

| Diretório | Finalidade |
| --- | --- |
| `app/` | Aplicação Java/Spring Boot, migrações Flyway e testes de integração. |
| `database/` | Orientações do banco e referência à localização das migrações. |
| `docs/` | Modelo, contrato da API, decisões e plano de implementação. |
| `scripts/` | Gerador de dados experimentais reproduzíveis. |
| `infra/` | Infraestrutura e instruções de execução. |
| `infra/app/` | Docker Compose e instruções de implantação da aplicação. |
| `infra/postgres/` | PostgreSQL e provisionamento de usuários. |
| `infra/redis/` | Redis, autenticação e configuração do cache. |
| `infra/network/` | Restrição de origem das conexões aos bancos. |
| `infra/scripts/` | Espaço reservado para futuros scripts de operação. |
| `load/` | Espaço reservado para cenários de carga com k6. |
| `monitoring/` | Espaço reservado para monitoramento e coleta de métricas. |
| `results/` | Resultados experimentais, ignorados pelo Git, exceto `.gitkeep`. |

## Estado do ambiente

| VM | IP | Estado registrado em 15/10/2026 |
| --- | --- | --- |
| tcc-app | 10.10.10.10 | Clientes PostgreSQL/Redis instalados; API ainda não implantada. |
| tcc-postgres | 10.10.10.20 | PostgreSQL implantado e comunicação autenticada validada. |
| tcc-redis | 10.10.10.30 | Redis implantado; aplicação ainda sem cache. |

A sincronização deste repositório não modifica as VMs. Implantação, migrações e reinícios seguem o procedimento documentado e exigem confirmação.

## Desenvolvimento no IntelliJ

Abra a pasta deste repositório e importe `app/pom.xml` como projeto Maven, ou abra diretamente esse arquivo. Configure o SDK Java 21. Abrir o projeto não inicia a aplicação nem altera os bancos das VMs.

Na raiz do repositório, com Java 21, Maven, Python 3 e Docker acessível:

```sh
mvn -f app/pom.xml verify
```

Os testes usam um PostgreSQL descartável local, independente das VMs. Arquivos `.env`, pastas `secrets/`, resultados de build e configurações locais de IDE não devem ser versionados. Os exemplos `.env.example` podem ser versionados.

## Documentação

- [Modelo, contrato e próximos passos](docs/IMPLEMENTACAO.md).
- [Aplicação, testes e exemplos HTTP](app/README.md).
- [Infraestrutura PostgreSQL e Redis](infra/README.md).
- [Registro de implantação dos bancos](infra/DEPLOYMENT.md).
- [Implantação preparada da API](infra/app/README.md).
- [Versões do ambiente](VERSIONS.md).

O código, infraestrutura e documentação produzidos anteriormente no espelho do projeto ChatGPT foram incorporados aqui. PDFs e referências sincronizadas em `sources/` permaneceram no espelho de origem; não fazem parte desta implementação.
