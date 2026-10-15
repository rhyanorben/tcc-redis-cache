# Implantação da API

Procedimento preparado, ainda não executado. A API fica na **tcc-app — 10.10.10.10**; PostgreSQL e Redis permanecem nas VMs de dados. Os passos alteram o ambiente e dependem de confirmação.

## 1. Provisionar PostgreSQL

Na tcc-postgres, revise `infra/postgres/provision-app.sql` e confirme que o banco `tcc` existe. Na pasta de infraestrutura, copie o arquivo revisado para o contêiner e execute:

```sh
cd ~/tcc-infra/infra/postgres
sudo docker compose cp provision-app.sql postgres:/tmp/provision-app.sql
sudo docker compose exec postgres psql -X -U tcc_admin -d tcc -f /tmp/provision-app.sql
```

O script cria `tcc_migrator`, `tcc_app` e o schema `tcc` numa transação. Se já existirem, pare e inspecione; não remova objetos nem reaplique sem revisão. Os prompts `\password` pedem senhas distintas para os dois usuários; não reutilize credenciais SSH ou administrativas. A migração concede à API acesso somente às tabelas de negócio, sem DDL ou acesso ao histórico Flyway.

## 2. Preparar a tcc-app

Verifique Docker e Compose antes de instalar o que faltar. Disponibilize o repositório completo, pois o build usa `app/`. Na raiz do projeto da VM:

```sh
cd infra/app
cp -n .env.example .env
install -d -m 700 secrets
```

Em Bash, grave as senhas definidas no provisionamento, sem imprimi-las ou sobrescrever arquivos existentes:

```sh
(umask 077; set -C; read -r -s -p 'Senha tcc_app: ' TCC_APP_SECRET; printf '\n'; printf '%s' "$TCC_APP_SECRET" > secrets/app_password.txt)
(umask 077; set -C; read -r -s -p 'Senha tcc_migrator: ' TCC_MIGRATION_SECRET; printf '\n'; printf '%s' "$TCC_MIGRATION_SECRET" > secrets/migration_password.txt)
chmod 644 secrets/app_password.txt secrets/migration_password.txt
docker compose --profile setup config --quiet
```

O diretório 700 protege os arquivos locais 644, legíveis pelo usuário do contêiner. Não versione os secrets. Use `sudo docker` se necessário, sem ampliar permissões do socket.

## 3. Migrar e iniciar

```sh
docker compose build
docker compose --profile setup run --rm migrate
```

Prossiga somente se a migração terminar com código zero:

```sh
docker compose up -d app
docker compose ps
docker compose logs --tail=100 app
curl --fail http://10.10.10.10:8080/actuator/health
```

`migrate` aplica Flyway e termina sem servidor HTTP. A API recebe apenas a credencial runtime e publica 8080 em `10.10.10.10`. O pool padrão tem dez conexões, configuráveis em `.env`. O cenário base mantém Redis desligado.

O build Docker ainda precisa ser validado. Antes dos ensaios, registre os digests das bases e da imagem final; use o mesmo artefato nos dois cenários. Não há TLS ou autenticação de usuários: use somente a rede experimental confiável.

## 4. Habilitar cache

Após validar a referência sem cache, siga [CACHE.md](../../docs/CACHE.md) para configurar o usuário Redis, secrets e sobreposições Compose. Essa etapa também está pendente de implantação.
