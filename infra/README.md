# PostgreSQL, Redis e rede

Os bancos já foram implantados; consulte o [registro](DEPLOYMENT.md). Os comandos abaixo documentam a preparação e operação. Iniciar, recriar, interromper ou reconfigurar serviços depende de confirmação; a documentação não autoriza mudanças nas VMs.

## Preparação

Cada serviço pertence à sua VM: PostgreSQL em `10.10.10.20` e Redis em `10.10.10.30`. Confirme IP, portas e Docker com `ip -br addr`, `ss -ltn`, `docker --version` e `docker compose version`. A rede `10.10.10.0/24` deve funcionar; a rede física de carga fica para depois.

Copie a pasta correspondente ou faça um checkout do projeto. Na raiz do repositório da **tcc-postgres**, para uma instalação nova:

```sh
cd infra/postgres
cp -n .env.example .env
install -d -m 700 secrets
(umask 077; set -C; openssl rand -hex 32 > secrets/postgres_password.txt)
chmod 644 secrets/postgres_password.txt
docker compose --env-file .env config --quiet
```

Na **tcc-redis**:

```sh
cd infra/redis
cp -n .env.example .env
install -d -m 700 secrets
(umask 077; set -C; openssl rand -hex 32 > secrets/redis_password.txt)
chmod 644 secrets/redis_password.txt
docker compose --env-file .env config --quiet
```

Gere senhas somente se os arquivos não existirem. `set -C` impede sobrescrita. O modo 644 permite leitura pelos usuários dos contêineres; o diretório 700 protege o acesso local. Compose secrets não é um cofre criptografado. Não versione `.env` e `secrets/`.

## Inicializar e verificar

Após confirmação, na pasta do serviço correspondente:

```sh
docker compose --env-file .env pull
docker compose --env-file .env up -d
docker compose ps
docker compose logs --tail=100
```

Na pasta PostgreSQL, verifique autenticação e versão:

```sh
docker compose exec postgres sh -c 'PGPASSWORD="$(cat /run/secrets/postgres_password)" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), version();"'
```

Na pasta Redis, espere `PONG`:

```sh
docker compose exec redis sh -c 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli --no-auth-warning ping'
```

Da **tcc-app**, com `psql` e `redis-cli`, valide o caminho entre VMs usando as senhas dos arquivos locais de cada serviço:

```sh
psql -h 10.10.10.20 -p 5432 -U tcc_admin -d tcc -W -c 'SELECT 1;'
redis-cli -h 10.10.10.30 -p 6379 --askpass ping
redis-cli -h 10.10.10.30 -p 6379 ping
```

A última chamada deve retornar `NOAUTH`. O healthcheck PostgreSQL verifica disponibilidade; a consulta autenticada verifica também a credencial.

## Configuração e limites

| Serviço | Decisões |
| --- | --- |
| PostgreSQL | Volume persistente, SCRAM-SHA-256, UTC e durabilidade padrão |
| Redis | Sem RDB/AOF ou volume; reinício deixa cache frio; `maxmemory=256mb`, `allkeys-lru` |
| Imagens | Digests fixados nos `.env.example`; versões em [VERSIONS.md](../VERSIONS.md) |

`POSTGRES_DB`, `POSTGRES_USER` e a senha inicial só atuam em volume vazio. Alterar os arquivos não muda credenciais existentes; não apague volumes para corrigir configuração nem troque a versão principal sem migração planejada. `tcc_admin` é administrativo; a API usa [roles separadas](app/README.md). A [ACL Redis da API](../docs/CACHE.md) está preparada, ainda não aplicada.

Não há TLS nem limites de CPU/RAM nos contêineres. Use apenas a rede experimental confiável e registre os recursos das VMs antes dos ensaios. O processo Redis pode consumir mais memória que `maxmemory`. Remoção de volumes/dados, inclusive `down -v`, exige confirmação.

## Restrição de rede

As portas são publicadas somente no IP interno de cada VM. `postgres/pg_hba.conf` permite PostgreSQL por loopback e pela origem `10.10.10.10`. Se houver NAT, confirme a origem efetiva antes de ajustar a regra; não amplie para todas as origens.

`network/restrict-service.sh` restringe em `DOCKER-USER` o tráfego TCP encaminhado às portas dos bancos à origem `10.10.10.10`, sem limpar regras ou alterar SSH. Foi instalado como `/usr/local/sbin/tcc-restrict-service`, com `tcc-network-guard.service` habilitado em ambas as VMs; o modelo usa `postgres`, e na VM Redis o argumento é `redis`.

A regra depende do backend iptables do Docker. UFW sozinho pode não controlar portas publicadas pelo Docker. A unidade acompanha reinícios do Docker, mas ainda não foi validada após reboot e pode haver uma janela antes da aplicação da regra. Mantenha a rede isolada e revalide após reinícios autorizados.
