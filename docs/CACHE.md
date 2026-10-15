# Cache-aside das páginas de pedidos

Implementado no código em 15/10/2026. Nenhuma VM foi alterada nesta etapa. Cache desligado por padrão; a API e as novas configurações Redis ainda não foram implantadas.

## Dois cenários da mesma aplicação

| Modo | Configuração | Comportamento |
| --- | --- | --- |
| Sem cache | `CACHE_ENABLED=false` | Consulta PostgreSQL diretamente; não cria conexão Redis nem tenta invalidá-lo. |
| Cache-aside | `CACHE_ENABLED=true` | Tenta ler a página no Redis; em falta, consulta PostgreSQL e armazena a resposta inteira com TTL. |

O endpoint, ordenação, limites e campos da resposta são os mesmos nos dois modos. Em hit não é aberta transação PostgreSQL. Em miss, empresa, conteúdo e contagem continuam usando o mesmo snapshot `REPEATABLE READ`.

A consulta do banco está em `PedidoService.listar`; a seleção entre os dois caminhos está em `ConsultaPedidosService`. A implementação Redis fica em `RedisPaginaCache` e usa JSON tipado de `PaginaPedidos`, sem serialização Java de objetos.

## Chaves e invalidação

```text
tcc:v1:tenant:{42}:pedidos:generation
tcc:v1:tenant:{42}:pedidos:<UUID>:page:0:size:20
```

`CACHE_NAMESPACE` identifica a versão/rodada e deve começar com `tcc:`. Empresa, versão, página e tamanho separam os resultados. A ordenação é fixa no contrato; mudar a consulta ou o formato exige um novo namespace.

A versão por empresa é um UUID, criado atomicamente se ausente. Depois de criar um pedido ou atualizar seu status, um evento transacional troca a versão **após o commit PostgreSQL**. Isso torna inacessíveis todas as páginas antigas da empresa, incluindo suas contagens. Rollback não invalida. Não há varredura KEYS/SCAN, limpeza global ou FLUSH no código da aplicação. As páginas antigas expiram pelo TTL.

A leitura verifica versão e página atomicamente. A gravação de uma página só é aceita se a versão lida antes da consulta ainda for a atual, usando Lua. Uma consulta iniciada antes da invalidação pode terminar com seu próprio snapshot antigo, mas não repopula uma versão nova. Não há garantia de leitura linearizável entre Redis e PostgreSQL: existe uma janela entre commit e invalidação e requisições já em andamento podem terminar depois da escrita.

A versão não tem TTL; uma chave pequena permanece por empresa acessada, sujeita à política de expulsão do Redis. Se ela for expulsa pelo `allkeys-lru`, um UUID novo evita reutilizar páginas de uma versão anterior. As páginas possuem TTL fixo de gravação; hits não renovam a expiração.

## Falhas e recuperação

Erros de conexão, timeout ou leitura inválida do cache não transformam uma leitura válida do banco em erro HTTP. Erros de negócio e PostgreSQL continuam propagados normalmente. Uma falha Redis após commit não desfaz a gravação já confirmada no banco.

Se a invalidação falhar, a instância guarda um marcador em memória para a empresa. Antes de voltar a ler o cache dessa empresa, tenta trocar a versão; enquanto não resolver, consulta o banco. Cada tentativa usa um UUID novo, inclusive em retries de comandos que possam ter sido executados antes de um timeout. Os marcadores pendentes são removidos após recuperação bem-sucedida; durante uma falha prolongada, ocupam uma entrada por empresa afetada.

Essa reparação vale para **uma instância da aplicação**, coerente com o ambiente inicial SIMT. Os marcadores não são duráveis nem compartilhados. Um encerramento entre commit e invalidação pode deixar páginas antigas até o TTL remanescente. Múltiplas instâncias exigiriam uma estratégia durável/compartilhada de invalidação; isso não foi implementado. Não há outbox nem proteção contra muitas consultas simultâneas para a mesma página fria.

Escritas SQL diretas, cargas do gerador, restaurações e gravações feitas com cache desligado não publicam eventos. Antes de habilitar/reabilitar cache nesses casos, use um namespace novo para a rodada; não reutilize páginas de outro estado da base. Não execute em paralelo aplicações com cache ligado e desligado escrevendo na mesma base para comparar leituras.

Redis é opcional para disponibilidade: `/actuator/health` continua avaliando PostgreSQL, sem falhar apenas pela indisponibilidade do cache. Falhas Redis são observadas pelos contadores e por um aviso limitado a um por 30 segundos por instância, sem senhas ou conteúdo de cache.

## Configuração

| Variável | Padrão | Finalidade |
| --- | --- | --- |
| `CACHE_ENABLED` | `false` | Habilita implementação Redis. |
| `CACHE_NAMESPACE` | `tcc:v1` | Prefixo da versão/rodada, até 64 caracteres e sem espaços. |
| `CACHE_TTL` | `60s` | TTL das páginas; permitido de 1ms a 1h. |
| `CACHE_TIMEOUT` | `200ms` | Timeout de conexão/comandos; permitido de 1ms a 5s. |
| `REDIS_HOST` | `10.10.10.30` | VM Redis. |
| `REDIS_PORT` | `6379` | Porta Redis. |
| `REDIS_USER` | `app` | Usuário da ACL da aplicação. |
| `REDIS_PASSWORD` | sem padrão | Obrigatória se cache habilitado; fornecida por secret. |

Os padrões são pontos de partida configuráveis, não parâmetros de desempenho já calibrados. Timeout de comando não é um limite global de latência HTTP; uma requisição pode realizar mais de um comando Redis. Não há circuit breaker; solicitações durante falhas ainda podem incorrer nos timeouts configurados.

## ACL e sobreposições Docker preparadas

O script Redis mantém o usuário administrativo `default` existente. Somente quando recebe `/run/secrets/redis_app_password`, cria o usuário `app` com hash SHA-256 da senha, chaves `~tcc:*` e permissões `+@connection +get +set +eval +evalsha`. Essa credencial precisa ter ao menos 32 caracteres e ser diferente da administrativa. A ACL restringe o prefixo da aplicação, não autentica nem separa usuários finais por empresa.

- Na VM Redis, `infra/redis/compose.app-user.yaml` adiciona o secret opcional ao Compose original.
- Na VM app, `infra/app/compose.cache.yaml` habilita cache e monta apenas a credencial do usuário `app`, com destino `REDIS_PASSWORD`.
- Sem essas sobreposições, a infraestrutura e a aplicação continuam no cenário anterior, sem exigir o secret Redis da aplicação.

Quando a execução nas VMs for autorizada, será necessário gerar uma senha nova, guardá-la em `secrets/redis_app_password.txt` nas duas pastas correspondentes, com diretório 700 e arquivo legível pelo usuário do contêiner. Não coloque a senha em `.env`, YAML ou Git.

Para **validar a configuração**, sem iniciar serviços, execute na raiz do repositório:

```sh
docker compose --env-file infra/redis/.env.example \
  -f infra/redis/compose.yaml -f infra/redis/compose.app-user.yaml config --quiet

docker compose --env-file infra/app/.env.example \
  -f infra/app/compose.yaml -f infra/app/compose.cache.yaml config --quiet
```

Usar essas sobreposições com `up` recria serviços e altera a ACL efetiva. A instalação segue pendente de autorização; não aplique os comandos às VMs por conta desta documentação. Primeiro implante e valide a referência sem cache, depois habilite o cenário com cache e registre namespace, TTL, timeout, versão da aplicação e condições da base.

## Métricas

Contadores Micrometer disponíveis dentro da aplicação:

- `tcc.cache.requests`, tag `result=hit|miss|fallback`: requisições atendidas pelo cache, faltas e consultas que desviaram por falha/pendência.
- `tcc.cache.errors`: falhas de operação Redis ou serialização; pode haver mais de uma por requisição.
- `tcc.cache.invalidations`: trocas de versão concluídas, incluindo reparações.
- `tcc.cache.discarded_writes`: páginas cuja gravação foi descartada por alteração de versão ou invalidação pendente.

404 e demais erros do banco não são armazenados. Um miss pode resultar em erro de negócio; portanto os contadores não equivalem apenas a respostas HTTP bem-sucedidas. Não há tag por empresa, para evitar crescimento da quantidade de séries. O endpoint de métricas não está exposto por padrão; a coleta externa e sua configuração ficam para a etapa de monitoramento.

## Testes

A suíte usa PostgreSQL e Redis descartáveis, sem conexão com as VMs. Redis é iniciado usando o script, configuração e ACL reais da infraestrutura, com senhas exclusivas dos testes. São verificados hits sem banco, equivalência da resposta, separação de empresas/páginas/tamanhos, invalidação após commit, ausência de invalidação em rollback, TTL, corrida de preenchimento, perda da chave de versão, JSON inválido, ACL e recuperação após uma pausa do contêiner Redis. O cenário sem cache verifica que não existe bean de conexão Redis.

## Referências

- [Spring Data Redis: execução de scripts](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Framework: eventos ligados a transações](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Redis: ACLs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).

Validação local concluída: **22 testes de integração, zero falhas e zero testes ignorados**, com PostgreSQL 17.11 e Redis 7.4.11 descartáveis. Build Java concluído e configurações Compose base/com cache validadas com `config --quiet`. O build da imagem Docker da aplicação e a implantação nas VMs permanecem pendentes.
