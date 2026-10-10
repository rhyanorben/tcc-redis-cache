# Ambiente experimental — PostgreSQL e Redis

Repositório do ambiente experimental do TCC de Engenharia de Computação. O objetivo é comparar o desempenho da mesma aplicação SaaS em arquitetura Single Instance Multi-Tenant (SIMT), na qual uma única instância atende múltiplos tenants, em duas configurações:

1. PostgreSQL como único serviço de armazenamento de dados.
2. PostgreSQL com Redis como camada de cache.

Esta etapa contém apenas a estrutura inicial do repositório. A aplicação, os serviços, os testes de carga e a infraestrutura serão implementados posteriormente.

| Diretório | Finalidade |
| --- | --- |
| `app/` | Código da aplicação Java/Spring Boot. |
| `database/` | Definições de esquema e scripts relacionados ao banco de dados. |
| `infra/` | Arquivos de infraestrutura e execução do ambiente experimental. |
| `infra/app/` | Configurações de infraestrutura da aplicação. |
| `infra/postgres/` | Configurações de infraestrutura do PostgreSQL. |
| `infra/redis/` | Configurações de infraestrutura do Redis. |
| `infra/scripts/` | Scripts de preparação e operação da infraestrutura. |
| `load/` | Cenários e testes de carga com k6. |
| `monitoring/` | Scripts e configurações de monitoramento e coleta de métricas. |
| `results/` | Resultados experimentais, ignorados pelo Git; o arquivo `.gitkeep` permite versionar o diretório. |

As versões das tecnologias serão fixadas em `VERSIONS.md` antes dos experimentos.
