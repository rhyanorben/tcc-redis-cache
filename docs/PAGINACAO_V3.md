# Paginação por visitas — protocolo 3

Esta revisão altera apenas a navegação da carga. A API, as consultas, os índices,
as escritas e o Redis permanecem como no protocolo 2. A cópia na tcc-load e o plano
estão preparados; os pilotos foram [aprovados em 30/10/2026](VALIDACAO_PAGINACAO_V3.md).
Os blocos ainda não foram iniciados. A preparação abaixo serve para reproduzir a instalação.

## Navegação

| Parâmetro | Regra |
| --- | --- |
| Visitas progressivas | Probabilidade de 90%; começam em 0 e avançam uma página por vez |
| Visitas regressivas | Probabilidade de 10%; começam em 0, vão à última e retornam uma página por vez |
| Duração da visita | Sorteio uniforme de 4 a 8 leituras bem-sucedidas; depois começa outra visita em 0 |
| Retorno local | Na visita progressiva, probabilidade de 10% de voltar uma página, quando possível |
| Leitura com erro | Mantém a página para a próxima tentativa de leitura; não inicia outra visita |
| Escrita entre leituras | Preserva a posição da navegação |
| Última página | Calculada pelo volume e tamanho da página, sem índice fixado manualmente |

Exemplos: `0 → 1 → 2 → 3 → nova visita em 0` e
`0 → 999 → 998 → 997 → nova visita em 0`. O usuário virtual pode continuar
enviando escritas entre essas leituras, conforme o perfil.

Os percentuais são probabilidades por visita, independentes dos perfis de leitura/escrita.
O número observado pode variar entre execuções. A quantidade de leituras por visita e
o retorno local são hipóteses explícitas de uso, sem atribuí-las a registros de produção.
As sementes preservam a sequência de decisões por usuário entre os modos; a duração
fixa pode produzir quantidades diferentes de operações e visitas.

`load/navigation.json` fixa esses parâmetros. O plano e a campanha registram a configuração;
mudanças após a preparação impedem a execução. Aquecimento e medição têm navegações
independentes, ambas começando em 0.

## Condições preservadas

Páginas de 20 pedidos; ordem `criadoEm DESC, id DESC`; mesma base e manifesto;
25 empresas ativas; perfis 100/0, 90/10, 70/30 e 50/50; 25, 50, 100, 250 e 500 VUs;
cinco repetições pareadas; 120 s de aquecimento somente leitura e 300 s de medição.
São 200 execuções em 20 blocos.

O ritmo continua sem pausa entre operações. As escritas continuam usando um pedido
exclusivo por VU e alternando status, como atualização controlada. Não foram adicionados
filtros, confirmação única por pedido ou novas regras de negócio. A invalidação continua
restrita às páginas da empresa alterada, após commit, com TTL de 60 s.

Assim, esta versão permite estudar o efeito da paginação por visitas sob pressão contínua.
Ela não representa integralmente tempos humanos de utilização nem um ciclo completo de pedidos.

## Preparar a cópia na geradora

No notebook, na raiz do repositório, crie um pacote novo:

```sh
python3 scripts/empacotar_paginacao.py \
  --saida results/preparacao-paginacao-v3/codigo-paginacao-v3.tar.gz
scp results/preparacao-paginacao-v3/codigo-paginacao-v3.tar.gz rhyan@10.20.20.40:/home/rhyan/
```

O pacote reúne somente fontes e guias do runner, sem `.env`, segredos ignorados ou
resultados anteriores. A criação não inicia carga nem acessa as VMs.

Na tcc-load, extraia em pasta nova e prepare o plano. Execute o bloco abaixo uma única
vez; ele para se a pasta já existir ou se faltar a referência anterior:

```sh
bash <<'SH'
set -euo pipefail
mkdir /home/rhyan/tcc-runner-v3
tar --extract --gzip --keep-old-files \
  --file /home/rhyan/codigo-paginacao-v3.tar.gz \
  --directory /home/rhyan/tcc-runner-v3
cd /home/rhyan/tcc-runner-v3
mkdir -p results/preparacao-paginacao-v3
cp --no-clobber /home/rhyan/tcc-runner-v2/results/campanha-20261024-v2/manifesto.json \
  results/preparacao-paginacao-v3/manifesto.json
python3 load/planejar.py --manifesto results/preparacao-paginacao-v3/manifesto.json \
  --seed 20261032 --saida results/plano-paginacao-v3
python3 load/blocos.py preparar --plano results/plano-paginacao-v3/plan.json \
  --manifesto results/preparacao-paginacao-v3/manifesto.json
SH
```

Esses comandos apenas copiam o código e preparam arquivos. Mantêm o backup existente
e os agentes já instalados nas VMs, sem alterar serviços. A preparação da campanha
recusa sobrescrever uma pasta de resultados existente.

## Conferência, piloto e blocos

Após a preparação na geradora, no notebook:

```sh
python3 scripts/executar_bloco.py --verificar
python3 scripts/executar_bloco.py --piloto
```

A conferência não envia carga. O segundo comando executa explicitamente um par
90/10 com 500 VUs, restauração, aquecimento e medição nos dois modos. Reserve 25 minutos.
O piloto fica fora da campanha. A checagem adicional `--piloto-leitura` executa somente
100/0 com cache e 500 VUs, com os mesmos tempos; reserve 12 minutos. Seu pacote fica
em `results/campanha-paginacao-v3/piloto-leitura-v3/piloto-capacidade.zip`.
Os dois pilotos já foram conferidos; o próximo passo é o bloco 1.

```sh
python3 scripts/executar_bloco.py --bloco 1
```

Use o [guia dos blocos](CAMPANHA_EM_BLOCOS.md) para acompanhamento, sequência e retomada.
O mínimo de carga continua em 70 min por bloco e 23h20 no total, além de preparação,
exportação e repetições. A campanha principal começa vazia em:

```text
/home/rhyan/tcc-runner-v3/results/campanha-paginacao-v3
```

## Resultados e compatibilidade

O resumo registra protocolo 3, parâmetros de navegação, número de visitas por direção
e contagens, erros e latências por classe de página: primeira, intermediária e última.
As latências por classe incluem as tentativas medidas, com os erros apresentados separadamente.
Uma classe não visitada tem latência ausente, nunca zero. O consolidado preserva
quantas repetições efetivamente observaram cada latência.

A consolidação ainda lê resultados do protocolo 2 separadamente, mas recusa misturar
protocolos ou configurações de navegação. Os scripts de execução aceitam apenas planos
novos do protocolo 3. Não atualize o fingerprint da campanha 2 para reaproveitá-la.

Os resultados e o PDF da campanha anterior permanecem preservados. Para o artigo da
nova campanha, substitua a descrição da distribuição aleatória 80/20 pela navegação
acima e use somente seus próprios resultados.
