# TCC — PostgreSQL e Redis

Experimento de Engenharia de Computação que compara a mesma aplicação com PostgreSQL e com cache-aside Redis. Uma instância atende várias empresas; a operação avaliada é a **listagem paginada de pedidos de uma empresa**.

## Estado atual

- API implementada com empresa, cliente, pedido e item_pedido.
- API implantada em 20/10/2026, com migração V1, usuários separados e ACL Redis da aplicação.
- Validação funcional nas VMs aprovada nos modos sem cache e com cache; atualmente o cache está habilitado, com TTL de 60 s e limite Redis de 1 GiB.
- Testes locais: 41 Java aprovados em 17/10; 53 Python, suíte Node e teste do script k6 aprovados em 20/10. Não são resultados de desempenho.
- Ethernet do computador 1 e segunda NIC da tcc-app configuradas em 21/10; comunicação e GET HTTP a partir da tcc-load confirmados.
- Base completa de 8.500.100 registros carregada em `tcc_experimento`; backup restaurado e conferido. Automação com autenticação manual e piloto 90/10 com 25 usuários validados; veja o [registro da preparação e do piloto](docs/PREPARACAO_E_PILOTO.md).

| VM | IP | Função |
| --- | --- | --- |
| tcc-app | 10.10.10.10 e 10.20.20.10 | API em Docker, porta 8080; gerenciamento local na porta 8081 |
| tcc-postgres | 10.10.10.20 | PostgreSQL |
| tcc-redis | 10.10.10.30 | Redis |

O [registro das VMs](infra/DEPLOYMENT.md) preserva o histórico e descreve a implantação de 20/10. O banco `tcc` preserva os dados da validação funcional anterior. A API experimental usa `tcc_experimento`, selecionado por uma sobreposição Compose. Backups, restauração, seleção do modo e coleta são coordenados pelos [hooks das VMs](infra/experiment/README.md). A campanha completa ainda não foi executada.

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
| Ethernet, validação e reversão | [infra/network/ETHERNET.md](infra/network/ETHERNET.md) |
| Protocolo, limites e campanha | [docs/EXPERIMENTO.md](docs/EXPERIMENTO.md) |
| Validações e pendências | [docs/VALIDACAO.md](docs/VALIDACAO.md) |
| Trocas exatas no texto do TCC | [docs/AJUSTES_TEXTO_TCC.md](docs/AJUSTES_TEXTO_TCC.md) |
| Carga e execução | [load/README.md](load/README.md) |
| Base completa, disco, backups e piloto | [docs/PREPARACAO_E_PILOTO.md](docs/PREPARACAO_E_PILOTO.md) |
| Versões | [VERSIONS.md](VERSIONS.md) |

`scripts/` reúne o gerador SQL, sem conexão ao banco, e a validação HTTP da implantação. `load/` prepara manifestos, plano, carga e consolidação; `monitoring/` coleta recursos e contadores. `results/` guarda resultados locais ignorados pelo Git. A comparação definitiva compreende 200 execuções. O piloto valida o procedimento e não substitui essa campanha.
