# TCC — PostgreSQL e Redis

Experimento de Engenharia de Computação que compara a mesma aplicação com PostgreSQL e com cache-aside Redis. Uma instância atende várias empresas; a operação avaliada é a **listagem paginada de pedidos de uma empresa**.

## Estado atual

- API implementada com empresa, cliente, pedido e item_pedido.
- Cache opcional, desligado por padrão; 41 testes Java aprovados em 17/10/2026. Em 20/10, 53 testes Python, a suíte Node e o teste local do script k6 foram aprovados.
- PostgreSQL e Redis implantados; em 16/10/2026 foram preparados monitoramento SQL e Redis com limite de 1 GiB.
- API, migrações, usuários da aplicação e ACL Redis pendentes de implantação.
- Gerador de dados, carga k6, planejamento pareado, coleta e consolidação preparados; piloto e campanha pendentes.

| VM | IP | Função |
| --- | --- | --- |
| tcc-app | 10.10.10.10 | API; possui apenas os clientes PostgreSQL/Redis instalados |
| tcc-postgres | 10.10.10.20 | PostgreSQL |
| tcc-redis | 10.10.10.30 | Redis |

O [registro das VMs](infra/DEPLOYMENT.md) separa as intervenções de 15 e 16/10/2026 da consulta após reinício em 17/10, quando as três VMs estavam desligadas. A API e a campanha não foram executadas nas VMs. Os modelos de restauração e limpeza dependem de configuração e autorização para o ambiente experimental dedicado.

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
| Protocolo, limites e campanha | [docs/EXPERIMENTO.md](docs/EXPERIMENTO.md) |
| Validações e pendências | [docs/VALIDACAO.md](docs/VALIDACAO.md) |
| Trocas exatas no texto do TCC | [docs/AJUSTES_TEXTO_TCC.md](docs/AJUSTES_TEXTO_TCC.md) |
| Carga e execução | [load/README.md](load/README.md) |
| Versões | [VERSIONS.md](VERSIONS.md) |

`scripts/` gera SQL sem acessar o banco. `load/` prepara manifestos, plano, carga e consolidação; `monitoring/` coleta recursos e contadores. `results/` guarda resultados locais ignorados pelo Git. A comparação definitiva compreende 200 execuções; não há resultados de desempenho ainda.
