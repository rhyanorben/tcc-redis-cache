# Execução nas VMs

## Pré-requisitos

Cada VM deve ter Linux, Docker Engine e o plugin Docker Compose disponíveis. Verifique `docker --version` e `docker compose version`. A instalação do Docker, alteração de grupos, firewall e serviços do sistema deve ser feita separadamente, com confirmação. Não execute os dois serviços no computador físico nem na mesma VM.

Confirme com `ip -br addr` que a VM possui o IP previsto e verifique se a porta está livre com `ss -ltn`. Copie a pasta correspondente e seus arquivos para a VM, ou use um checkout do repositório. Todos os comandos abaixo partem da raiz do projeto na VM indicada.

A rede `10.10.10.0/24` deve estar funcional antes da inicialização. A rede física `10.20.20.0/24` e o gerador de carga ficam para depois.

## Preparar arquivos locais

Na **tcc-postgres**:

```sh
cd infra/postgres
cp -n .env.example .env
install -d -m 700 secrets
# Execute apenas se o arquivo ainda não existir; não substitua uma senha existente.
(umask 077; set -C; openssl rand -hex 32 > secrets/postgres_password.txt)
chmod 644 secrets/postgres_password.txt
docker compose --env-file .env config --quiet
```

Na **tcc-redis**:

```sh
cd infra/redis
cp -n .env.example .env
install -d -m 700 secrets
# Execute apenas se o arquivo ainda não existir.
(umask 077; set -C; openssl rand -hex 32 > secrets/redis_password.txt)
chmod 644 secrets/redis_password.txt
docker compose --env-file .env config --quiet
```

Os arquivos de senha precisam ser legíveis pelos usuários internos das imagens, por isso têm modo 644, dentro de uma pasta local 700. Compose monta esses arquivos como secrets; isso não é um cofre criptografado. Não versione nem compartilhe `.env` e `secrets/`. Use senhas diferentes para os dois serviços. O Redis aceita a senha gerada sem a quebra de linha final.

## Inicialização — somente após confirmação

Os comandos desta seção alteram serviços. Foram documentados, mas não executados nesta entrega. Após autorizar a inicialização, execute na pasta do serviço da VM correspondente:

```sh
docker compose --env-file .env pull
docker compose --env-file .env up -d
docker compose --env-file .env ps
docker compose --env-file .env logs --tail=100
```

Os exemplos agora fixam os digests das imagens efetivamente validadas em 15/10/2026 (PostgreSQL 17.11 e Redis 7.4.11). Para futuras atualizações, tags podem mudar: antes dos experimentos, registre os digests das imagens utilizadas com `docker image inspect IMAGEM --format '{{json .RepoDigests}}'`, fixe `POSTGRES_IMAGE` e `REDIS_IMAGE` em `imagem@sha256:...` e mantenha os mesmos digests em todas as rodadas. Não troque a versão principal de PostgreSQL em um volume existente sem planejar migração.

## Verificar após a inicialização

Na pasta PostgreSQL, o teste abaixo exige senha e executa apenas uma consulta:

```sh
docker compose exec postgres sh -c 'PGPASSWORD="$(cat /run/secrets/postgres_password)" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), version();"'
```

Na pasta Redis:

```sh
docker compose exec redis sh -c 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli --no-auth-warning ping'
```

Espere `PONG`. O healthcheck do PostgreSQL verifica disponibilidade; a consulta acima também verifica autenticação. O healthcheck Redis verifica PING autenticado.

Na **tcc-app**, com os clientes `psql` e `redis-cli` instalados, valide o caminho entre VMs. As ferramentas pedirão as senhas, que devem ser obtidas pelos arquivos locais de cada VM sem publicar seu conteúdo:

```sh
psql -h 10.10.10.20 -p 5432 -U tcc_admin -d tcc -W -c 'SELECT 1;'
redis-cli -h 10.10.10.30 -p 6379 --askpass ping
```

Um teste negativo de Redis, sem senha, deve retornar `NOAUTH`:

```sh
redis-cli -h 10.10.10.30 -p 6379 ping
```

O acesso TCP do PostgreSQL é permitido no `pg_hba.conf` apenas para loopback e a origem `10.10.10.10`. A publicação Docker normalmente preserva a origem entre VMs Linux; se houver NAT intermediário, confirme a origem nos logs antes de ajustar a regra. Não amplie para `0.0.0.0/0`.

## Decisões e limites

- PostgreSQL usa volume nomeado persistente, SCRAM-SHA-256 e horário UTC. As opções padrão de durabilidade permanecem habilitadas. A etapa inicial dos bancos não criou schema de negócio. O schema e o gerador de dados estão agora preparados em `app/` e `scripts/`, mas ainda não foram aplicados às VMs.
- `tcc_admin`, criado pela imagem oficial, é administrador do banco. Não deve ser a credencial da futura aplicação; crie um usuário de privilégio mínimo ao implementar o schema e suas migrações.
- Alterações em `POSTGRES_DB`, `POSTGRES_USER` e no arquivo de senha só inicializam um volume vazio. Trocar `.env` ou o arquivo não altera usuários/senhas de um banco existente. Não apague o volume para corrigir isso.
- Redis é cache descartável: RDB e AOF estão desabilitados, sem volume de dados. Reinícios deixam o cache frio. O limite inicial de 256 MiB e a política `allkeys-lru` são hipóteses de configuração, a revisar conforme a memória da VM e registrar na metodologia. A memória total do processo pode exceder `maxmemory`.
- Redis usa o usuário `default` autenticado, com permissões administrativas para esta etapa de infraestrutura. A ACL restrita `app` está agora preparada no script e em `compose.app-user.yaml`, mas ainda não foi aplicada às VMs. Consulte `../docs/CACHE.md`.
- As portas são publicadas apenas no IP interno de cada VM. Isso não restringe a origem dos clientes Redis. Antes da execução, revise as regras de acesso para permitir `10.10.10.10` e negar outras origens nas portas dos serviços. Portas publicadas pelo Docker podem contornar regras comuns de UFW; valide o encaminhamento Docker/firewall efetivamente, sem aplicar regras genéricas que possam cortar SSH.
- Não há TLS nesta etapa: use somente a rede experimental isolada e confiável. Senhas e dados não possuem criptografia de transporte.
- A configuração não impõe limites de CPU/RAM ao contêiner. Dimensionamento de VMs, limites e estado inicial do cache devem ser controlados e registrados antes dos ensaios.
- Não execute `down -v`, remoção de volumes, limpeza de dados ou recriação de serviços sem confirmação. Até `stop`, `restart` e `up` afetam disponibilidade e exigem confirmação neste projeto.

## Referências técnicas

- [Imagem oficial PostgreSQL](https://hub.docker.com/_/postgres): inicialização, secrets e persistência.
- [Segurança Redis](https://redis.io/docs/latest/operate/oss_and_stack/management/security/): autenticação, rede e modo protegido.
- [ACL Redis](https://redis.io/docs/latest/management/security/acl/): configuração de usuários e hashes.

## Validação desta entrega

A validação inicial foi estática. Após autorização para acessar e preparar as VMs, os serviços foram instalados, iniciados e testados. Consulte [o registro de implantação](DEPLOYMENT.md) para versões, locais e evidências.


## Restrição de origem implementada nas VMs

O script `network/restrict-service.sh` adiciona uma regra específica em `DOCKER-USER`, sem limpar regras existentes. Ele filtra somente o sentido original das conexões TCP encaminhadas às portas publicadas, permitindo a origem `10.10.10.10`. Não altera a porta SSH. Depende do backend iptables do Docker usado nesta implantação.

Uma cópia root-owned foi instalada em `/usr/local/sbin/tcc-restrict-service`. A unidade `tcc-network-guard.service` está habilitada nas duas VMs, com o argumento correspondente. Seu modelo está em `network/tcc-network-guard.service.example`; na VM Redis o argumento é `redis`. A unidade executa após Docker e acompanha reinícios do serviço. A reaplicação após reboot ainda não foi testada; por executar após Docker, não garante ausência de uma janela durante a inicialização. Mantenha a rede experimental isolada e valide novamente as regras após reinícios. Alterações futuras de firewall exigem confirmação.
