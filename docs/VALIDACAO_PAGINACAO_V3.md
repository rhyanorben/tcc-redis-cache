# Validação da paginação — 30/10/2026

**Ambiente preparado para iniciar o bloco 1.** O runner está instalado em
`/home/rhyan/tcc-runner-v3`, com 200 execuções em 20 blocos na campanha
`campanha-paginacao-v3`. Nenhum bloco foi iniciado. A campanha anterior foi preservada.

## Conferência e pilotos

API, PostgreSQL, Redis, rede, relógios, backup, imagens, índices e orçamento de disco
passaram pela conferência. A base contém 100 empresas, 500 mil clientes, 2 milhões
de pedidos e 6 milhões de itens. Foram mantidos os recursos das VMs e a imagem da API.

Cada caso abaixo teve restauração, 120 s de aquecimento e 300 s de medição.
Os números da tabela se referem somente à medição, com 500 usuários virtuais.

| Perfil | Cache | Requisições | Erros | Visitas progressivas | Acertos do cache |
| --- | --- | ---: | ---: | ---: | ---: |
| 90/10 | Habilitado | 131.901 | 0 | 89,73% | 18,39% |
| 90/10 | Desabilitado | 115.456 | 0 | 89,69% | Não se aplica |
| 100/0 | Habilitado | 2.012.716 | 0 | 90,08% | 99,70% |

Os aquecimentos também terminaram sem erros. Na medição, não houve recusa de capacidade,
escrita incerta, violação do contrato HTTP ou falha de cache. Todas as classes de
página foram observadas; as visitas regressivas ficaram próximas dos 10% previstos.
A verificação determinística da semente do piloto cobriu outras 100 mil leituras
simuladas, sem saltos inválidos, incluindo `0 → 1 → 2` e `0 → 999 → 998`.

No caso 100/0, a CPU média do k6 correspondeu a 75,9% das quatro vCPUs, abaixo do
critério de atenção sustentada de 80% usado pelo runner. O pico chegou a 98,4% e a
memória a 72,95%. Isso pede acompanhamento do primeiro bloco e preservação das
condições de execução. Os pilotos verificam o funcionamento; não substituem as
cinco repetições de cada cenário nem permitem concluir o efeito definitivo do cache.

## Integridade e encerramento

Os dois ZIPs passaram pela conferência de hash, CRC e inventário: 85 arquivos
verificados. Os nove resumos de monitoramento foram recalculados a partir dos dados
brutos e coincidiram com os arquivos salvos, com 60 amostras de recursos por serviço
em cada medição. Fontes, manifesto, janelas, sementes e exclusão dos pilotos da
campanha também foram conferidos.

Ao final, um GET na tcc-load retornou HTTP 200 pela Ethernet, com página 0,
20 registros e 1.000 páginas para a empresa consultada. As sessões temporárias e
os processos dos pilotos foram encerrados. A internet permaneceu pelo Wi-Fi.

Evidências locais, ignoradas pelo Git:

- `results/campanha-paginacao-v3/conferencia.json`
- `results/campanha-paginacao-v3/piloto-capacidade.zip`
- `results/campanha-paginacao-v3/piloto-leitura-v3/piloto-capacidade.zip`
- `results/campanha-paginacao-v3/auditoria-20261030/`

## Próxima execução

No notebook:

```sh
cd /home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache
python3 scripts/executar_bloco.py --bloco 1
```

A previsão é de 1h20–1h45 por bloco; reserve duas horas. Confira o ZIP do
bloco 1 antes de iniciar uma sequência. Depois, `--blocos 2-20` executa os restantes
na ordem, com autenticação no início e retomada dos pares pendentes em caso de falha.
Os 20 blocos continuam estimados em 27–35 horas, além de pausas e repetições.
Consulte o [guia de execução e retomada](CAMPANHA_EM_BLOCOS.md).
