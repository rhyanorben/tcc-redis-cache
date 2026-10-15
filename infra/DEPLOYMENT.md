# Registro de implantação — 15/10/2026

Preparação executada via SSH com autorização do usuário. Nenhum dado ou serviço anterior foi removido. As VMs de dados não tinham Docker instalado nem escuta nas portas 5432 e 6379.

| VM | Resultado |
| --- | --- |
| tcc-postgres — 10.10.10.20 | Docker Engine 29.9.1, Compose 5.6.0, PostgreSQL 17.11 saudável |
| tcc-redis — 10.10.10.30 | Docker Engine 29.9.1, Compose 5.6.0, Redis 7.4.11 saudável |
| tcc-app — 10.10.10.10 | Instalados apenas clientes PostgreSQL/Redis para verificação; aplicação não criada |

## Arquivos e credenciais

Nas VMs de dados, a infraestrutura está em `/home/rhyan/tcc-infra/infra/`. Cada serviço usa sua pasta `postgres/` ou `redis/`. Os arquivos `.env` locais fixam os mesmos digests dos exemplos deste projeto. Os exemplos e a documentação foram sincronizados novamente após a validação.

Senhas diferentes, aleatórias e com 64 caracteres hexadecimais foram geradas nas VMs, sem usar a senha SSH:

- PostgreSQL: `/home/rhyan/tcc-infra/infra/postgres/secrets/postgres_password.txt` na tcc-postgres.
- Redis: `/home/rhyan/tcc-infra/infra/redis/secrets/redis_password.txt` na tcc-redis.

Os valores não estão neste registro ou no versionamento. As pastas `secrets/` têm modo 700 e os arquivos 644 para leitura pelos usuários internos dos contêineres. Os comandos remotos com credenciais não foram gravados no histórico da sessão.

## Verificações executadas

- Ambos os contêineres ficaram `healthy` e publicados somente nos respectivos IPs internos.
- Da tcc-app, consulta autenticada retornou banco `tcc`, usuário `tcc_admin` e PostgreSQL 17.11.
- Da tcc-app, Redis autenticado retornou `PONG` e versão 7.4.11.
- Redis sem senha retornou `NOAUTH`; PostgreSQL com senha inválida rejeitou a conexão.
- PostgreSQL confirmou diretório `/var/lib/postgresql/data`, UTC e SCRAM-SHA-256.
- Redis confirmou limite 268435456 bytes, `allkeys-lru`, AOF desligado e ausência de snapshots RDB.
- Conexões do computador físico às duas portas expiraram por bloqueio; SSH permaneceu acessível.
- A unidade de restrição de rede ficou habilitada nas duas VMs. Não foram feitos testes de reinício ou remoção de volumes.

## Operação

Na VM correspondente:

```sh
cd ~/tcc-infra/infra/postgres  # ou redis, na outra VM
sudo docker compose ps
sudo docker compose logs --tail=100
sudo systemctl status tcc-network-guard.service --no-pager
sudo iptables -vnL DOCKER-USER
```

Use `sudo` para administrar Docker; o usuário não foi adicionado ao grupo Docker. As instalações seguiram o [repositório oficial Docker para Ubuntu](https://docs.docker.com/engine/install/ubuntu/). A instalação dos pré-requisitos também atualizou curl e suas bibliotecas; não foi realizada atualização geral do sistema.

Permanecem para etapas futuras: backup e teste de restauração, teste de reinicialização autorizada, dimensionamento definitivo, usuário PostgreSQL da aplicação, ACL Redis da aplicação e implementação Spring Boot. A persistência do PostgreSQL está configurada, mas ainda não foi testada por reinicialização. Nenhum experimento de carga foi executado.
