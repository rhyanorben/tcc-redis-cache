# Contratos dos hooks

Esta pasta não contém hooks executáveis. O runner interrompe a execução se faltar qualquer hook.
Uma implementação deve ser revisada para o ambiente escolhido antes de usar `--executar`.

Cada hook é um executável externo que recebe a configuração por variáveis de ambiente,
termina com código zero e escreve exclusivamente um recibo JSON em stdout. Logs vão para stderr.
Os recibos não substituem as verificações reais descritas abaixo.

Variáveis comuns: `RUN_ID`, `RUN_DIR`, `PROFILE`, `VUS`, `SEED`, `CACHE_MODE` (`on` ou `off`),
`BASE_URL`, `MANIFEST_PATH`, `MANIFEST_SHA256`, `BACKUP_PATH`, `BACKUP_SHA256`,
`MEASUREMENT_SUMMARY`.

| Executável | Responsabilidade | Campos adicionais ao recibo |
|---|---|---|
| `restore` | Restaurar o backup previamente validado em um banco experimental dedicado, preservar IDs e conferir o manifesto. Não tocar bancos alheios. | `backup_sha256`, `manifest_sha256` |
| `mode` | Configurar o cache no modo solicitado, aguardar a API ficar pronta e comprovar o modo efetivo. | `cache_mode` |
| `clear` | Esvaziar fisicamente o cache experimental, incluindo gerações e páginas antigas, e confirmar ausência de entradas. | `cache_empty: true` |
| `verify` | Conferir saúde, contagens e IDs reais do manifesto, 25 empresas ativas, os 20 pedidos reservados ABERTO por empresa e o modo efetivo. Não escrever dados. | `cache_mode`, `base_matches_manifest: true`, `reserved_orders_open: true` |
| `monitor-start` | Iniciar coletores nas três VMs e aguardar a primeira amostra válida de cada serviço antes de retornar. | `monitoring_ready: true`, `services: ["app", "postgres", "redis"]` |
| `monitor-stop` | Esperar o término das requisições, obter a amostra final de cada serviço, encerrar os coletores e consolidar as amostras usando `MEASUREMENT_SUMMARY`. | `monitoring_stopped: true` |

Todo recibo também exige `"hook": "nome-exato"` e `"completed": true`.
Exemplo de formato, que não executa procedimento algum:

```json
{"hook":"mode","completed":true,"cache_mode":"on"}
```

A ordem é restore → mode → clear → verify → aquecimento somente leitura → monitor-start →
medição → monitor-stop. Não limpar o cache entre aquecimento e medição.
O runner chama monitor-stop também após falhas, mas a ausência de resumo k6 pode impedir
a consolidação. O hook deve encerrar processos mesmo nesse caso e devolver erro se não
puder produzir resumos válidos.

O monitoramento deve permanecer ativo até após `measurement_completed_unix_ms`, não
somente até o término nominal de 300 segundos. Iniciar coleta por pelo menos 360 segundos
ou usar processo encerrado pelo hook; aguardar amostra posterior ao término e à drenagem.
Manter o ambiente sem tráfego de negócio externo antes/depois da janela. As consultas de
observação são somente leitura e usam a role de monitoramento. Preservar o filtro pelo
usuário `tcc_app` e as entradas individuais de `pg_stat_statements` para separar o tráfego
da aplicação das consultas dos coletores.

O hook monitor-stop escreve os três arquivos:

```text
$RUN_DIR/monitoring/app-summary.json
$RUN_DIR/monitoring/postgres-summary.json
$RUN_DIR/monitoring/redis-summary.json
```

Cada arquivo exige `service`, `scope: "measurement_resources_with_bracketed_counters"` e
`measurement_window` com os mesmos `measurement_start_unix_ms`, `measurement_end_unix_ms`
e `measurement_completed_unix_ms` do resumo k6. Use `monitoring/resumir.py` para delimitar
a janela; deltas de contadores usam amostras imediatamente anteriores/posteriores à
janela e podem incluir pequenas margens. CPU/memória usam as amostras dentro dos 300 segundos.

O hash de arquivo garante identidade do backup, não sua restaurabilidade. Antes da campanha,
é necessário um ensaio de restauração e validação desse mesmo backup. Nenhum hook real de
restauração, limpeza ou reinicialização é fornecido nesta pasta.
