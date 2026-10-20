# Registro das VMs — 15/10/2026

Preparação anterior executada via SSH com autorização. Não foram removidos dados ou serviços existentes. Este registro descreve aquela execução; não confirma o estado remoto atual.

| VM | Resultado registrado |
| --- | --- |
| tcc-postgres — 10.10.10.20 | Docker 29.9.1, Compose 5.6.0 e PostgreSQL 17.11 saudável |
| tcc-redis — 10.10.10.30 | Docker 29.9.1, Compose 5.6.0 e Redis 7.4.11 saudável |
| tcc-app — 10.10.10.10 | Clientes PostgreSQL/Redis instalados; API pendente |

## Arquivos e credenciais

Nas VMs de dados, cada serviço usa `/home/rhyan/tcc-infra/infra/postgres/` ou `/home/rhyan/tcc-infra/infra/redis/`. Os `.env` fixam os digests registrados em [VERSIONS.md](../VERSIONS.md).

Senhas distintas de 64 caracteres hexadecimais foram geradas sem reutilizar a senha SSH. Estão em `secrets/postgres_password.txt` e `secrets/redis_password.txt`, nas respectivas pastas das VMs. Os diretórios têm modo 700 e os arquivos 644 para leitura dos contêineres. As credenciais não foram versionadas nem incluídas neste registro.

## Validação executada

- Contêineres `healthy`, publicados nos respectivos IPs internos.
- Da tcc-app, PostgreSQL autenticado confirmou banco `tcc`, usuário `tcc_admin` e versão; Redis autenticado retornou `PONG`.
- PostgreSQL rejeitou senha inválida; Redis sem senha retornou `NOAUTH`.
- PostgreSQL confirmou persistência em `/var/lib/postgresql/data`, UTC e SCRAM-SHA-256.
- Redis confirmou 256 MiB, `allkeys-lru` e ausência de AOF/RDB.
- Portas dos bancos bloquearam o computador físico; SSH permaneceu acessível.
- Restrição de rede habilitada nas duas VMs; reinicialização ainda não testada.

## Consultar o ambiente

Na VM PostgreSQL, ou trocando a primeira pasta por `redis` na outra VM:

```sh
cd ~/tcc-infra/infra/postgres
sudo docker compose ps
sudo docker compose logs --tail=100
sudo systemctl status tcc-network-guard.service --no-pager
sudo iptables -vnL DOCKER-USER
```

A administração usa `sudo`; o usuário não foi adicionado ao grupo Docker. A instalação seguiu o [repositório oficial para Ubuntu](https://docs.docker.com/engine/install/ubuntu/), sem atualização geral do sistema.

Pendem implantação da API, usuários e migrações de negócio, ACL Redis da aplicação, backup/restauração, teste de persistência após reinício e dimensionamento definitivo. Nenhum ensaio de carga foi executado.


## Alinhamento experimental — 16/10/2026

Intervenção posterior autorizada, preservando os registros e os volumes existentes. A data desta seção corresponde à execução, não à revisão desta documentação.

| VM | Confirmação |
| --- | --- |
| tcc-app | 2 vCPU e 4 GiB; API ainda não implantada |
| tcc-postgres | 2 vCPU e 4 GiB; PostgreSQL 17.11 e extensão `pg_stat_statements` 1.11 |
| tcc-redis | 1 vCPU e 2 GiB; Redis 7.4.11, `maxmemory=1gb`, `allkeys-lru`, sem RDB/AOF |

PostgreSQL foi reiniciado com `pg_stat_statements` carregado, preservando o volume de dados. A configuração anterior foi copiada com identificação `20261016T125141Z`. A role de monitoramento foi provisionada para consulta de estatísticas, sem escrita nas tabelas de negócio; sua credencial fica somente na VM PostgreSQL, em `secrets/monitor_password.txt`, com modo 600. Não é uma credencial da API e não deve ser versionada.

O limite Redis foi ajustado em execução para 1 GiB por `CONFIG SET` e persistido no arquivo de configuração, sem reinício, limpeza de chaves ou alteração de persistência. A configuração anterior foi copiada com identificação `20261016T125215Z`. Isso atualiza o limite de 256 MiB registrado na seção histórica de 15/10.

Não foram aplicadas migrações de negócio, carregada a base de 8,5 milhões de registros, implantada a API ou executada campanha de carga. ACL Redis da aplicação, roles de negócio, backup/restauração da base experimental e integração dos hooks continuam pendentes de implantação e validação. A configuração local preparada de coleta/carga não significa que esses procedimentos foram executados remotamente.


## Consulta após reinício do host — 17/10/2026

A consulta ao libvirt após reinício do computador físico mostrou as três VMs de serviço desligadas. A inicialização das VMs PostgreSQL e Redis foi bloqueada pela revisão automática de aprovação antes da execução; nenhuma VM foi iniciada e nenhum serviço foi alterado nesta data.

As configurações e validações de 16/10 permanecem como registro histórico. Não houve nova verificação ao vivo de PostgreSQL, Redis, credenciais, persistência ou recursos internos em 17/10. A retomada do ambiente continua pendente.

No computador de desenvolvimento, em contêineres Docker descartáveis, os 41 testes Java e os nove testes do gerador passaram em 17/10/2026. Esses testes verificam correção funcional e não constituem resultados de desempenho nem uma validação das VMs.


## Consulta de estado — 20/10/2026

A consulta somente leitura ao libvirt confirmou `tcc-app`, `tcc-postgres` e `tcc-redis` desligadas. Não foram iniciadas VMs nem revalidados os serviços por SSH. As intervenções de 16/10 permanecem como histórico; a confirmação dos serviços em execução depende de autorização específica para ligar as VMs.
