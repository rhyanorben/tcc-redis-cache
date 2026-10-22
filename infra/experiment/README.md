# Execução nas VMs do TCC

A preparação de 22/10/2026 usa `tcc_experimento` na VM PostgreSQL. O banco `tcc` anterior permanece separado, com seus registros de validação. A API mantém a mesma imagem; `infra/app/compose.experiment.yaml` seleciona o banco experimental e as sobreposições Ethernet/cache preservam a rede e o modo escolhidos.

## Dados, índices e backup

A base contém 100 empresas, 500.000 clientes, 2.000.000 pedidos e 6.000.000 itens. O gerador valida contagens por empresa, três itens por pedido e totais antes do commit. Datas e valores são determinísticos. Os índices da migração V1 permanecem iguais nos dois modos; não criar ou remover índices durante a campanha.

O volume lógico PostgreSQL foi ampliado para 32 GiB usando espaço já disponível no disco virtual de 40 GiB. A base inicial ocupa aproximadamente 1,3 GB. O backup de referência tem cerca de 40 MB e foi restaurado integralmente em `tcc_validacao_restore`; as contagens e os dois milhões de pedidos inicialmente ABERTO foram conferidos antes de remover somente essa cópia temporária.

| Arquivo | Local |
| --- | --- |
| Backup dos dados anteriores | PostgreSQL: `/home/rhyan/tcc-experimento/backups/tcc-antes-experimento.dump` |
| Referência experimental | PostgreSQL: `/home/rhyan/tcc-experimento/backups/base-v1.dump` |
| Segunda cópia, no computador 2 | Geradora: `/home/rhyan/tcc-experimento/base-v1.dump` |
| Manifesto com IDs reais | Geradora: `/home/rhyan/tcc-runner/results/preparacao-base-v1/manifesto.json` |
| Plano completo | Geradora: `/home/rhyan/tcc-runner/results/plano-base-v1/plan.json` |

SHA-256 da referência: `84af910f36b945af6080fc8bb8df2a39835dfa388cd81689ab40483a64baa58f`. Confirme identidade e espaço antes de restaurar. O agente recusa outro banco, ausência da identificação experimental, hash divergente, conexões da aplicação ainda abertas e menos de 5 GiB livres na VM PostgreSQL. Reserve pelo menos 12 GiB livres no notebook para crescimento das imagens e resultados; não acumule cópias integrais por execução.

O backup é criado uma vez e preservado. Cada ensaio restaura essa referência no mesmo banco experimental, sem criar novas cópias permanentes. Arquivos, logs e resumos de medição devem usar diretórios novos e permanecer fora do Git.

## Autenticação manual

Não foram instaladas regras sudo sem senha nem mantidas novas chaves de acesso. O operador autentica três sessões temporárias SSH/sudo na geradora. Elas são usadas pelos hooks durante o ensaio e encerradas ao final. Senhas não são gravadas em código, configuração ou resultados.

Os agentes e coletores ficam em `/opt/tcc-experiment` nas VMs de serviço, com configuração root em `/etc/tcc-experiment.json`. A conexão às VMs privadas passa pelo SSH da tcc-app; PostgreSQL, Redis e métricas permanecem sem publicação na Ethernet experimental.

Para reinstalar os arquivos, em cada VM de serviço a partir de uma cópia do repositório, escolha `app`, `postgres` ou `redis` conforme a VM:

```sh
tcc_service=app
sudo install -d -m 755 /opt/tcc-experiment
sudo install -o root -g root -m 644 infra/experiment/remote_agent.py \
  infra/experiment/session_worker.py monitoring/coletar.py \
  load/exportar_manifesto.sql /opt/tcc-experiment/
sudo install -o root -g root -m 600 \
  "infra/experiment/config-$tcc_service.json.example" /etc/tcc-experiment.json
```

Confira os caminhos e o hash do backup nos exemplos antes de instalar a configuração. Essa instalação não cria regras sudo, chaves ou serviços de inicialização. Na geradora, mantenha o repositório em `~/tcc-runner` e as identidades SSH já conferidas em `~/tcc-experimento/ssh/known_hosts`; confirme as identidades dos servidores antes de aceitar mudanças. A API precisa ter `compose.experiment.yaml` ao lado do Compose existente.

Na tcc-load, em um terminal:

```sh
cd ~/tcc-runner
sudo python3 infra/experiment/manual_session.py
```

Informe as credenciais de cada VM. Aguarde `TCC_MANUAL_READY` e mantenha o terminal aberto. A sessão expira em uma hora por padrão; para uma campanha previamente planejada, ajuste `--lifetime-seconds` ao tempo necessário. O socket local é restrito ao root. Ctrl+C encerra as sessões e remove o socket.

Em outro terminal, use o executor existente com os hooks reais:

```sh
cd ~/tcc-runner
sudo python3 load/executar.py --plano results/plano-base-v1/plan.json \
  --hooks "$PWD/load/hooks.vm" \
  --backup /home/rhyan/tcc-experimento/base-v1.dump \
  --backup-sha256 84af910f36b945af6080fc8bb8df2a39835dfa388cd81689ab40483a64baa58f \
  --base-url http://10.20.20.10:8080 --saida results/novo-ensaio \
  --limite 2 --executar
```

O plano usado no piloto começa com um par 90/10, 25 usuários, semente `20261032`. `--limite 2` executa somente esse par; remover o limite inicia a matriz completa e exige decisão explícita sobre a campanha. Não reutilizar um diretório de saída.

## Hooks e coleta

A ordem é parar a API → restaurar → selecionar modo → limpar Redis → conferir manifesto → aquecer → iniciar coletores → medir → aguardar a última amostra → encerrar coletores e resumir.

A restauração é transacional e preserva proprietários, IDs e permissões do dump. A base é analisada novamente antes do aquecimento. A verificação confere os IDs reservados, estados ABERTO, contagens por empresa, banco efetivo e modo da API. A limpeza recusa chaves Redis fora do prefixo `tcc:`. O modo exige a imagem já validada, sem reconstrução.

Os três coletores iniciam antes da medição e só são encerrados após uma amostra posterior à conclusão das requisições. O PostgreSQL é observado com `--database tcc_experimento`, mantendo o filtro pelo usuário `tcc_app`. Os resumos recortam os 300 segundos de medição; falhas de fronteira ou de coleta invalidam a execução. Os dados brutos ficam nas VMs e são exportados para o diretório do ensaio.

## Retorno à aplicação anterior

Encerrar carga e coletores. Parar a API na tcc-app:

```sh
cd ~/tcc-app/infra/app
sudo docker compose -f compose.yaml stop app
```

Na VM Redis, limpar o cache dedicado antes de trocar de banco, pois os mesmos IDs podem existir nas duas bases:

```sh
sudo python3 /opt/tcc-experiment/remote_agent.py clear
```

Na tcc-app, usar somente as configurações anteriores, sem `compose.experiment.yaml`:

```sh
cd ~/tcc-app/infra/app
sudo docker compose -f compose.yaml -f compose.ethernet.yaml -f compose.cache.yaml up -d --no-build app
```

Isso volta ao banco `tcc` original, que foi preservado. Não remover bancos ou volumes como parte dessa troca. A expansão do volume lógico não deve ser revertida por redução do sistema de arquivos.
