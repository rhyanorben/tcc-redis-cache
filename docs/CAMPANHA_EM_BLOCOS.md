# Campanha em blocos

A campanha revisada usa o protocolo 2 e a pasta `campanha-20261024-v2`. Os resultados de `campanha-20261023` permanecem preservados para diagnóstico e não entram nesta comparação. **Após conferir o piloto, recomece pelo bloco 1**, mesmo tendo concluído o bloco 1 anterior. Veja o [motivo da revisão](REVISAO_CAPACIDADE.md).

Execute os comandos no terminal do notebook, na pasta abaixo. A carga ocorre na tcc-load. São 20 blocos, com cinco pares e dez execuções por bloco, preservando a ordem e as sementes do plano original. Cada execução tem 120 s de aquecimento e 300 s de medição.

```sh
cd /home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache
```

| Etapa | Comando | Estimativa |
| --- | --- | --- |
| Conferência sem carga | `python3 scripts/executar_bloco.py --verificar` | 1–3 min, mais autenticação |
| Piloto de capacidade: dois modos, 500 usuários | `python3 scripts/executar_bloco.py --piloto` | 16–22 min; reserve 25 min |
| Primeiro bloco da revisão | `python3 scripts/executar_bloco.py --bloco 1` | 1h20–1h45 |
| Sequência de quatro blocos | `python3 scripts/executar_bloco.py --blocos 2-5` | 5h20–7h; reserve 8h |
| Outro bloco | Mesmo comando `--bloco`, trocando o número | 1h20–1h45 |
| Consolidação dos 20 blocos | `python3 scripts/executar_bloco.py --consolidar` | 1–5 min |

O mínimo por bloco é 70 minutos de carga. Restauração, início da API, conferências e exportação acrescentam tempo. Reserve duas horas por bloco; os 20 representam aproximadamente 27–35 horas, além das pausas e repetições de pares interrompidos. A correção ainda precisa ser observada sob carga. Primeiro execute o piloto de capacidade e apresente seu ZIP para conferência; depois execute o bloco 1 e confira o pacote antes de deixar uma sequência longa.

## Iniciar e acompanhar

A revisão foi implantada e a conferência sem carga passou. Comece pelo piloto manual:

```sh
python3 scripts/executar_bloco.py --piloto
```

Ele repete somente o par 90/10 com 500 usuários que revelou a falha, nos dois modos e com a mesma semente. Usa os tempos e preparações completos, mas salva em pasta própria e não conta como execução dos blocos. Envie `results/campanha-20261024-v2/piloto-capacidade.zip` para validar antes de iniciar `--bloco 1`. Nenhuma carga é iniciada automaticamente pela instalação ou pela conferência.

O comando abre o terminal persistente `tcc-campanha-v2` e solicita SSH/sudo da geradora e as credenciais das três VMs de serviço. Aguarde a autenticação das três antes de se ausentar. As senhas não são gravadas; não há chave permanente nem sudo sem senha.

Um bloco mantém a sessão por até quatro horas. Na sequência, o limite é de duas horas por bloco solicitado, mais duas horas de margem, com mínimo de quatro horas. Não há nova autenticação entre blocos. A sequência para na primeira falha ou ao terminar o intervalo e encerra as sessões.

Mantenha ambos os computadores na energia, o cabo Ethernet e as quatro VMs em funcionamento, com a tampa do notebook aberta. O comando impede temporariamente a suspensão do notebook. No Windows, mantenha suspensão e reinicializações automáticas desativadas durante a execução. Evite outros trabalhos pesados e consultas manuais à API durante a medição.

Para fechar somente a visualização, pressione Ctrl+B e depois D. Para voltar:

```sh
tmux attach -t tcc-campanha-v2
```

Após a mensagem final, pressione Enter. As VMs podem ser desligadas entre blocos concluídos; preserve as configurações ao ligá-las novamente. Para interromper manualmente, pressione Ctrl+C e aguarde a exportação parcial.

## Resultados e retomada

Os pacotes são atualizados após cada par e ao encerrar o bloco, na geradora:

```text
/home/rhyan/tcc-runner-v2/results/campanha-20261024-v2/exports/
```

Ao terminar o bloco ou a sequência, inclusive por falha, os pacotes disponíveis são copiados e conferidos por hash no notebook:

```text
results/campanha-20261024-v2/bloco-01.zip
results/campanha-20261024-v2/bloco-01.zip.sha256
...
results/campanha-20261024-v2/bloco-20.zip
```

Na sequência, a cópia ocorre ao final para evitar disputa de rede/disco com a medição. Se a conexão impedir a cópia, os pacotes já salvos permanecem na geradora. Recupere um bloco sem executar carga novamente:

```sh
python3 scripts/executar_bloco.py --recolher 1
```

O piloto fica separado em `/home/rhyan/tcc-runner-v2/results/piloto-capacidade-v2/exports/piloto-capacidade.zip` e é copiado para a pasta local da campanha. Seu registro identifica a exclusão da consolidação. Os ZIPs de bloco contêm plano, manifesto, parâmetros, recibos, tentativas, resumos k6, dados brutos dos serviços e recursos da geradora/notebook, com inventário `SHA256.json`. Os resultados ficam fora do Git. Apresente os ZIPs do piloto e, depois, do primeiro bloco antes de avançar.

Nos blocos, para retomar após falha, repita o mesmo comando. Os pares completos desta campanha são preservados; os dois modos do par incompleto são repetidos em nova tentativa. Blocos posteriores não são iniciados após erro. Um bloco já completo somente reexporta o pacote. Blocos anteriores precisam estar completos para continuar.

Após os 20 blocos, `--consolidar` exige os 100 pares completos e seleciona somente a tentativa validada de cada par. Salva `summary.json`, `groups.csv` e `paired.csv` em `consolidacao.zip`, também copiado para o notebook. Um bloco isolado não fornece as cinco repetições de todos os cenários.

## Proteções e leitura dos erros

O protocolo 2 distingue saturação comprovadamente anterior à escrita de resultado incerto. O 503 identificado por `DATABASE_CAPACITY_EXCEEDED`, `operationApplied=false` e tipo `urn:tcc:problem:database-capacity` conta como erro/recusa e permite continuar. Timeout, 500, 503 genérico ou resposta de escrita fora do contrato interrompem a execução. Erros HTTP de leitura são medidos; HTTP 200 fora do contrato invalida o caso.

Os resumos separam tentativas, sucessos, recusas e falhas incertas, com vazão e latências de sucesso próprias. Recusas não são convertidas em sucesso. O [protocolo](EXPERIMENTO.md) detalha esse tratamento.

Uma trava impede campanhas simultâneas. Antes de cada par são conferidos relógios, backup, imagem, índices, recursos, código e parâmetros. Mudanças durante a campanha são recusadas. As reservas são de 12 GiB no notebook, 2 GiB na geradora e 5 GiB na VM PostgreSQL; perder o acompanhamento do notebook interrompe o bloco. Não amplie volumes nem altere parâmetros para contornar uma falha: preserve o pacote e apresente o diagnóstico.
