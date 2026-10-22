# Monitoramento experimental

Os scripts coletam e resumem dados de cada execução. A validação automatizada usa dados sintéticos; os [hooks das VMs](../infra/experiment/README.md) também foram conferidos com serviços reais. A base completa e o monitoramento do piloto estão registrados em [PREPARACAO_E_PILOTO.md](../docs/PREPARACAO_E_PILOTO.md). A campanha completa permanece pendente.

## Preparação

Execute o coletor na própria VM de cada serviço, com Python 3 e acesso administrativo ao Docker local. Os exemplos abaixo partem da raiz da cópia do repositório presente nessa VM. O diretório de saída deve existir e cada nome de arquivo deve ser novo: os scripts recusam sobrescrita.

Antes da campanha, confira a sincronização dos relógios das três VMs de serviço e do gerador:

```sh
timedatectl show -p NTPSynchronized --value
```

O resultado deve ser `yes`; confira também o desvio informado pelo serviço de sincronização usado no ambiente. Relógios sincronizados são uma condição do protocolo. Informar UTC nos arquivos não corrige diferenças entre os relógios.

| Serviço | Origem |
| --- | --- |
| Aplicação | Docker e `http://127.0.0.1:8081/actuator/metrics`; a porta administrativa permanece publicada somente no loopback da VM |
| PostgreSQL | Docker e `pg_stat_statements`, filtrado pelo usuário `tcc_app`; conexão local no contêiner com a role restrita `tcc_monitor` |
| Redis | Docker e `INFO all`; a credencial administrativa é lida do secret dentro do contêiner e não é gravada na saída |

A opção `--database` seleciona o banco das estatísticas; seu padrão continua `tcc`. No experimento isolado, informe `tcc_experimento`.

O provisionamento PostgreSQL está em `infra/postgres/provision-monitoring.sql`. A role de monitoramento possui acesso às estatísticas e padrão de transação somente leitura; não recebe leitura ou escrita nas tabelas de negócio. A autenticação local usada pelo coletor ocorre dentro do contêiner e depende da configuração local de `pg_hba.conf`.

O coletor não restaura bases, troca o modo da API nem limpa o Redis. Essas operações pertencem à preparação da execução e às integrações explícitas do executor descritas em `docs/EXPERIMENTO.md`.

## Coleta por VM

Depois do aquecimento de 120 s e da drenagem de suas requisições, inicie os três coletores. Aguarde pelo menos uma amostra completa e válida de cada serviço antes de iniciar a medição. Os comandos abaixo executam por 360 s e amostram a cada 5 s.

Na `tcc-app`:

```sh
mkdir -p results/ensaio-001/monitoring
sudo python3 monitoring/coletar.py --service app \
  --compose infra/app/compose.yaml \
  --output results/ensaio-001/monitoring/app.jsonl \
  --duration 360 --interval 5
```

Na `tcc-postgres`:

```sh
mkdir -p results/ensaio-001/monitoring
sudo python3 monitoring/coletar.py --service postgres \
  --compose infra/postgres/compose.yaml --database tcc_experimento \
  --output results/ensaio-001/monitoring/postgres.jsonl \
  --duration 360 --interval 5
```

Na `tcc-redis`:

```sh
mkdir -p results/ensaio-001/monitoring
sudo python3 monitoring/coletar.py --service redis \
  --compose infra/redis/compose.yaml \
  --output results/ensaio-001/monitoring/redis.jsonl \
  --duration 360 --interval 5
```

Use terminais separados ou a integração de monitoramento do executor. A coleta precisa começar antes da medição e continuar após o término de suas requisições. Nenhum tráfego de negócio, inclusive verificações manuais, pode ocorrer nessas margens. Não inicie outra execução enquanto seus contadores finais ainda estiverem sendo coletados.

Os 360 s cobrem uma medição de 300 s e margens de início e drenagem quando os processos são coordenados. Eles não garantem cobertura se o gerador atrasar; nesse caso, refaça a coleta. O coletor registra `timestamp` e `completed_at` para cada amostra e encerra com erro se alguma leitura falhar.

## Resumo por execução

Reúna os três JSONL e o `measurement-summary.json` produzido pelo k6 no mesmo diretório de execução. Para cada serviço:

```sh
python3 monitoring/resumir.py results/ensaio-001/monitoring/app.jsonl \
  --measurement-summary results/ensaio-001/measurement-summary.json \
  --output results/ensaio-001/monitoring/app-summary.json

python3 monitoring/resumir.py results/ensaio-001/monitoring/postgres.jsonl \
  --measurement-summary results/ensaio-001/measurement-summary.json \
  --output results/ensaio-001/monitoring/postgres-summary.json

python3 monitoring/resumir.py results/ensaio-001/monitoring/redis.jsonl \
  --measurement-summary results/ensaio-001/measurement-summary.json \
  --output results/ensaio-001/monitoring/redis-summary.json
```

O arquivo k6 informa `measurement_start_unix_ms`, `measurement_end_unix_ms` e `measurement_completed_unix_ms`. A janela nominal tem 300 s. O horário de conclusão pode ser posterior ao fim nominal porque requisições iniciadas durante a medição precisam terminar.

O resumo mantém duas janelas distintas:

- **Recursos:** utiliza somente amostras cujo início e conclusão estão inteiramente dentro dos 300 s nominais. Amostras que cruzam as fronteiras são excluídas. CPU e memória são resumos das amostras disponíveis; não há interpolação nem estimativa dos valores nas fronteiras.
- **Contadores:** subtrai a última amostra concluída antes do início da medição da primeira iniciada após a conclusão do k6. Assim, inclui operações em drenagem. As margens precisam permanecer sem tráfego de negócio; o resumo registra essa exigência, mas não consegue comprovar sua ausência sozinho.

A distância máxima permitida entre cada fronteira e sua amostra é de 15 s, configurável com `--max-boundary-gap-seconds`. Ausência de cobertura, erros de coleta, timestamps sem fuso, regressão de relógio, substituição de contêiner, reinício de processo ou redução de contadores invalidam o resumo. Alterações de configuração Redis e resets ou descarte de estatísticas PostgreSQL também são recusados, inclusive quando aparecem em amostras intermediárias e os valores se recuperam depois.

Sem `--measurement-summary`, o resultado descreve toda a coleta e recebe `scope: collection`. Esse modo serve para diagnóstico; não recorta os 300 s e não constitui um resultado da campanha.

## Interpretação

O acerto lógico de páginas é `hit / (hit + miss + fallback)`, calculado sobre as diferenças dos contadores da aplicação. Se não houve acessos, o resultado é `null`. Registre os três desfechos separadamente. `keyspace_hits` e `keyspace_misses` do Redis incluem acessos auxiliares e não representam esse indicador.

As diferenças de `pg_stat_statements` incluem consultas executadas pelo usuário `tcc_app`; uma requisição HTTP pode produzir várias consultas SQL. Consultas novas partem de zero. Consultas desaparecidas, contadores reduzidos e mudanças de `stats_reset` ou `dealloc` invalidam o resumo. Não é necessário zerar estatísticas globais entre execuções.

CPU usa a porcentagem reportada pelo Docker, que pode ultrapassar 100% quando mais de um núcleo é utilizado. Memória Docker representa o consumo reportado para o contêiner. `used_memory`, `used_memory_dataset` e `used_memory_rss` descrevem aspectos distintos do Redis; `maxmemory` é seu limite configurado, não o teto de memória total do processo.

Os coletores também consomem recursos. Comandos administrativos Redis contribuem para estatísticas gerais, como `total_commands_processed`; preserve o mesmo intervalo e procedimento nos dois modos. Preserve os JSONL originais, confira lacunas e não substitua uma coleta inválida por um resumo parcial.

## Validação local

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s monitoring/tests -v
```

Os testes verificam parsing de unidades, deltas, reinícios e resets intermediários, seleção da role de monitoramento e proteção de credenciais na montagem das consultas e comandos, além do recorte temporal e da drenagem. Eles não acessam serviços ou VMs nem comprovam permissões efetivas ou sincronização dos relógios do ambiente.
