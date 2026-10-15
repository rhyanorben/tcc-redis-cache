# Implantação da aplicação — preparada, ainda não aplicada

Apenas na VM `tcc-app` (10.10.10.10). PostgreSQL continua na VM 10.10.10.20 e Redis na 10.10.10.30. O Compose base usa PostgreSQL, sem cache. A sobreposição `compose.cache.yaml` prepara o segundo cenário. Os comandos abaixo ficam para execução após confirmação, pois criam roles, tabelas e um novo serviço.

## 1. Provisionar usuários PostgreSQL

Na VM PostgreSQL, copiar e revisar `infra/postgres/provision-app.sql`. O banco `tcc` deve existir. Execute o SQL em sessão interativa como administrador:

```sh
cd ~/tcc-infra/infra/postgres
sudo docker compose exec postgres psql -X -U tcc_admin -d tcc
```

Dentro do psql, use `\i /CAMINHO/NO/CONTEINER/provision-app.sql` após copiar o arquivo para o contêiner, ou cole o conteúdo revisado do script. O script cria `tcc_migrator`, `tcc_app` e o schema `tcc` numa transação. Se roles/schema existirem, pare e inspecione, sem apagar ou reaplicar cegamente. Os dois comandos `\password` pedirão senhas diferentes, sem imprimi-las. Não reutilize a senha SSH nem a senha administrativa. As permissões de tabelas são concedidas pela migração e não abrangem o histórico Flyway.

## 2. Preparar a VM app

Docker e Compose ainda precisam ser verificados/instalados na VM app. O repositório completo, incluindo `app/`, deve estar disponível, pois o build usa esse caminho.

Na raiz do projeto na tcc-app:

```sh
cd infra/app
cp -n .env.example .env
install -d -m 700 secrets
```

Crie `secrets/app_password.txt` e `secrets/migration_password.txt` com os valores definidos por `\password`, sem espaços ou quebra de linha ao final. Use entrada oculta para evitar histórico, por exemplo em Bash:

```sh
(umask 077; set -C; read -r -s -p 'Senha tcc_app: ' TCC_APP_SECRET; printf '\n'; printf '%s' "$TCC_APP_SECRET" > secrets/app_password.txt)
(umask 077; set -C; read -r -s -p 'Senha tcc_migrator: ' TCC_MIGRATION_SECRET; printf '\n'; printf '%s' "$TCC_MIGRATION_SECRET" > secrets/migration_password.txt)
chmod 644 secrets/app_password.txt secrets/migration_password.txt
docker compose --profile setup config --quiet
```

A pasta 700 protege os arquivos locais 644, que precisam ser legíveis pelo usuário sem privilégios do contêiner. Não versione os arquivos. Use `sudo docker` se necessário; não amplie permissões do socket.

## 3. Migrar e iniciar — requer confirmação

```sh
docker compose build
docker compose --profile setup run --rm migrate
# Prossiga somente se a migração terminar com código zero.
docker compose up -d app
docker compose ps
docker compose logs --tail=100 app
curl --fail http://10.10.10.10:8080/actuator/health
```

A execução `migrate` aplica Flyway e termina sem servidor HTTP. A API não recebe o secret do migrador e não executa DDL. Ela publica 8080 somente em 10.10.10.10. Não há frontend, Redis, TLS ou autenticação de usuários. Use apenas na rede de laboratório confiável; o cabeçalho de empresa não é autenticação. Atualizações de firewall, instalação e reinícios continuam sujeitos a confirmação.

As imagens base do Dockerfile usam tags; o build Docker ainda não foi validado. Antes dos ensaios, valide o build na VM, registre os digests das bases e da imagem final e mantenha o mesmo artefato nos cenários sem/com cache. O pool tem dez conexões por padrão, configurável em `.env`; registre essa configuração na metodologia.


## Cenário posterior com cache

O cenário base e a migração definem `CACHE_ENABLED=false` e não exigem credencial Redis. Depois de validar a API sem cache, a integração opcional usa `compose.cache.yaml` e o usuário Redis restrito `app`. Consulte [o procedimento e as limitações](../../docs/CACHE.md). A configuração foi preparada, mas nenhum usuário, secret ou serviço das VMs foi alterado neste incremento.
