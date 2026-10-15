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
