# Carga experimental

Execute os comandos a partir da raiz do repositório. Python 3 e Node.js bastam para validar
e preparar arquivos. A execução real usa Docker com k6 **1.6.0**, fixado também por digest
em `planejar.py`. Não há resultados de campanha neste diretório.

A matriz contém quatro perfis leitura/escrita (`100-0`, `90-10`, `70-30`, `50-50`), cinco
concorrências (25, 50, 100, 250, 500 VUs), cache ligado/desligado e cinco repetições:
**200 execuções**, com 120 s de aquecimento somente leitura e 300 s de medição cada.
São pelo menos 23h20, além da preparação e coleta. As mesmas 25 empresas ficam ativas em
todas as concorrências. Cada VU usa um pedido exclusivo e alterna seu status, preservando
o volume da base. Erro de escrita interrompe a execução; o aquecimento exige requisições.
Erros HTTP de leitura são registrados como desfechos de carga, sem invalidar automaticamente
o caso. Resposta HTTP 200 com corpo fora do contrato invalida e interrompe a execução.

As consultas usam páginas de 20 pedidos, ordenadas por `criadoEm DESC, id DESC`. Para cada
empresa, 80% das leituras escolhem as primeiras 200 das 1.000 páginas; as demais escolhem as
outras 800. Cada bloco completo de 100 operações contém a proporção planejada de escritas;
o último bloco pode ficar incompleto. Sementes pareadas reproduzem as decisões por VU,
mas a duração fixa pode gerar quantidades de requisições diferentes entre modos.

## Preparar o manifesto e o plano

Primeiro gere e carregue a base definitiva descrita em `docs/EXPERIMENTO.md`. O exportador
SQL abaixo faz somente leitura e exige 100 empresas do lote, com 5.000 clientes, 20.000 pedidos
e 60.000 itens por empresa. Ele reserva os IDs reais de 20 pedidos `ABERTO` por empresa.
Execute a exportação na rede privada com uma role que tenha `SELECT` nessas tabelas. A opção `-q` evita misturar mensagens SQL ao CSV. Na geradora, os hooks acessam o PostgreSQL por SSH através da tcc-app; a porta do banco permanece privada.

```bash
mkdir -p results/preparacao
psql -X -q -h 10.10.10.20 -U tcc_app -d tcc_experimento \
  -v lote=base-v1 -f load/exportar_manifesto.sql > results/preparacao/pedidos.csv
python3 load/criar_manifesto.py --csv results/preparacao/pedidos.csv \
  --lote base-v1 --saida results/preparacao/manifesto.json
python3 load/planejar.py --manifesto results/preparacao/manifesto.json \
  --seed 20261017 --saida results/plano-exp-001
python3 load/executar.py --plano results/plano-exp-001/plan.json --limite 2
```

A última etapa é **preview**: não chama hooks, Docker, API ou VMs. Manifesto e plano usam
arquivos/diretórios novos; não sobrescrevem uma preparação anterior.

## Executar após preparar os hooks

`hooks.vm/` implementa os seis contratos para as VMs do TCC. Use o procedimento de
[autenticação manual e execução](../infra/experiment/README.md): as sessões temporárias
precisam estar abertas antes de iniciar o executor. `hooks.example/README.md` descreve os
contratos para outros ambientes. O destino atual é o banco dedicado `tcc_experimento`.

Com hooks reais instalados, backup validado e destino conferido, a forma de execução é:

```bash
python3 load/executar.py --plano results/plano-exp-001/plan.json \
  --hooks /caminho/absoluto/hooks-revisados \
  --backup /caminho/absoluto/base-validada.dump \
  --backup-sha256 HASH_SHA256_PREVIAMENTE_CONFERIDO \
  --base-url http://10.20.20.10:8080 --saida results/campanha-exp-001 --executar
```

Os caminhos e o hash acima são parâmetros que precisam ser substituídos. `--limite N` permite
um piloto dos primeiros casos e não equivale à campanha completa. A ordem por caso é:
restaurar → configurar modo → limpar cache → verificar base → aquecer → iniciar coleta →
medir → encerrar coleta. Não limpe o cache entre aquecimento e medição. Recibos, logs e resumos
ficam no diretório da execução; falhas geram `invalid.json` e interrompem o runner.

## Consolidar e verificar

```bash
python3 load/resumir.py --resultados results/campanha-exp-001 \
  --saida results/consolidacao-exp-001
python3 -m unittest discover -s load/tests -v
node --test load/tests/workload.test.js
```

A consolidação exige cinco repetições nos dois modos de cada cenário presente, além de
conclusão confirmada e monitoramento das três VMs na janela correta. Ela rejeita smoke tests,
execuções inválidas e métricas ausentes entre repetições. Um subconjunto completo de cenários
pode ser consolidado, mas somente os 20 cenários completos representam a campanha definitiva.
Os arquivos gerados são `summary.json`, `groups.csv` e `paired.csv`, com média, mediana,
desvio padrão amostral e diferenças pareadas. Média de p95/p99 por repetição não é percentil
global. Métricas disponíveis em apenas um modo ficam identificadas no JSON.
