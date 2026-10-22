# Implantação da API

API implantada e validada em **20/10/2026**, na tcc-app — `10.10.10.10`. PostgreSQL e Redis permanecem nas VMs de dados. Desde 21/10, também publica HTTP em `10.20.20.10:8080`, com GET validado a partir da tcc-load. O código está em `~/tcc-app`; o cache está habilitado. Veja [Ethernet experimental](../network/ETHERNET.md). Este guia registra a implantação e permite repetir as verificações; novos provisionamentos devem começar pela inspeção do ambiente.

## 1. Provisionar PostgreSQL

Na tcc-postgres, revise `infra/postgres/provision-app.sql` e confirme que o banco `tcc` existe. Na pasta de infraestrutura, copie o arquivo revisado para o contêiner e execute:

```sh
cd ~/tcc-infra/infra/postgres
sudo docker compose cp provision-app.sql postgres:/tmp/provision-app.sql
sudo docker compose exec postgres psql -X -U tcc_admin -d tcc -f /tmp/provision-app.sql
```

O script cria `tcc_migrator`, `tcc_app` e o schema `tcc` numa transação; os prompts `\password` definem senhas distintas antes do commit. Não reutilize credenciais SSH ou administrativas. As roles e a migração V1 já existem no ambiente atual: não reaplique esse provisionamento. A API tem acesso às tabelas de negócio, sem criação de objetos no schema ou acesso ao histórico Flyway.

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
sudo chown "$(id -un):10001" secrets/app_password.txt secrets/migration_password.txt
chmod 640 secrets/app_password.txt secrets/migration_password.txt
sudo docker compose --profile setup config --quiet
```

O diretório 700 protege os secrets locais; arquivos 640 permitem leitura pelo operador e pelo grupo 10001 do contêiner, sem leitura para outros usuários. Aplique o mesmo proprietário e modo ao secret Redis na tcc-app. Não versione credenciais nem amplie permissões do socket Docker.

## 3. Nova instalação: migrar e iniciar

```sh
sudo docker compose build
sudo docker compose --profile setup run --rm migrate
```

Prossiga somente se a migração terminar com código zero:

```sh
sudo docker compose up -d app
sudo docker compose ps
sudo docker compose logs --tail=100 app
curl --fail http://127.0.0.1:8081/actuator/health
```

`migrate` aplica Flyway e termina sem servidor HTTP. A API recebe apenas a credencial runtime e publica 8080 em `10.10.10.10`. A porta administrativa 8081 publica somente no loopback da VM e fornece `health` e `metrics` para verificação/coleta local. O pool padrão tem dez conexões, configuráveis em `.env`. O cenário base mantém Redis desligado.

Build, migração e execução foram validados em 20/10. O ID da imagem e o JRE constam em [VERSIONS.md](../../VERSIONS.md); preserve o mesmo artefato nos dois cenários. Antes da campanha, registre também os digests das bases. Não há TLS ou autenticação de usuários: use somente a rede experimental confiável.

## 4. Habilitar cache

A ACL e os secrets Redis já estão configurados. No ambiente atual, mantenha também `compose.ethernet.yaml` para preservar a publicação experimental. O modo atual usa namespace `tcc:vm-validacao-20261020`, TTL de 60 s e timeout de 200 ms. Mantenha a sobreposição ao consultar ou atualizar a API com cache:

```sh
cd ~/tcc-app/infra/app
sudo docker compose -f compose.yaml -f compose.cache.yaml -f compose.ethernet.yaml ps
sudo docker compose -f compose.yaml -f compose.cache.yaml -f compose.ethernet.yaml logs --tail=100 app
```

Na VM Redis, use `-f compose.yaml -f compose.app-user.yaml`, preservando a ACL. Veja [CACHE.md](../../docs/CACHE.md).


## 5. Repetir a validação funcional

O script cria duas empresas próprias e verifica os modos em sequência; não apaga registros existentes. Use manifesto e relatórios novos em cada execução completa. A fase com cache altera um pedido, portanto não deve ser repetida isoladamente sobre o manifesto já utilizado.

Na tcc-app, com o script atualizado disponível em `scripts/validar_implantacao.py`, escolha um diretório novo e desligue o cache, preservando a publicação Ethernet:

```sh
cd ~/tcc-app
TCC_VALIDATION_DIR="results/implantacao-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$TCC_VALIDATION_DIR"
cd infra/app
sudo docker compose -f compose.yaml -f compose.ethernet.yaml up -d --no-build app
curl --fail http://127.0.0.1:8081/actuator/health
cd ../..
python3 scripts/validar_implantacao.py --phase sem-cache \
  --manifest "$TCC_VALIDATION_DIR/manifesto.json" \
  --output "$TCC_VALIDATION_DIR/sem-cache.json"
```

Prossiga somente após aprovação da primeira fase. Habilite a sobreposição e execute a segunda fase com o mesmo manifesto:

```sh
cd infra/app
sudo docker compose -f compose.yaml -f compose.cache.yaml -f compose.ethernet.yaml up -d --no-build app
curl --fail http://127.0.0.1:8081/actuator/health
cd ../..
python3 scripts/validar_implantacao.py --phase cache \
  --manifest "$TCC_VALIDATION_DIR/manifesto.json" \
  --output "$TCC_VALIDATION_DIR/cache.json"
```

Aguarde a API ficar saudável após cada recriação antes de executar o script. Mantenha o mesmo terminal para preservar `TCC_VALIDATION_DIR`; a execução deve ocorrer sem outra carga concorrente. Os relatórios ficam ignorados pelo Git. Na implantação de 20/10, foram aprovadas 357 checagens sem cache e 104 com cache; não constituem ensaio de desempenho. A base definitiva, a restauração, o piloto e a campanha continuam pendentes. A configuração Ethernet e sua reversão estão em [ETHERNET.md](../network/ETHERNET.md).
