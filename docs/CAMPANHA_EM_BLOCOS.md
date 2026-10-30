# Campanha em blocos

A campanha de paginação usa o protocolo 3 e a pasta `campanha-paginacao-v3`. Os 20 blocos do protocolo 2 permanecem preservados. Esta revisão muda somente a navegação, conforme o [protocolo de paginação por visitas](PAGINACAO_V3.md). Instalação, plano e pilotos foram [conferidos em 30/10/2026](VALIDACAO_PAGINACAO_V3.md); o próximo passo é o bloco 1. Para reproduzir a instalação, siga o guia de paginação. Nenhuma carga é iniciada automaticamente.

Execute os comandos no terminal do notebook, na pasta abaixo. A carga ocorre na tcc-load. São 20 blocos, com cinco pares e dez execuções por bloco, preservando a ordem e as sementes do plano original. Cada execução tem 120 s de aquecimento e 300 s de medição.

```sh
cd /home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache
```

| Etapa | Comando | Estimativa |
| --- | --- | --- |
| Conferência sem carga | `python3 scripts/executar_bloco.py --verificar` | 1–3 min, mais autenticação |
| Piloto de capacidade: dois modos, 500 usuários | `python3 scripts/executar_bloco.py --piloto` | 16–22 min; reserve 25 min |
| Capacidade em 100/0 com cache, 500 usuários | `python3 scripts/executar_bloco.py --piloto-leitura` | 8–12 min |
| Primeiro bloco da revisão | `python3 scripts/executar_bloco.py --bloco 1` | 1h20–1h45 |
| Sequência de quatro blocos | `python3 scripts/executar_bloco.py --blocos 2-5` | 5h20–7h; reserve 8h |
| Outro bloco | Mesmo comando `--bloco`, trocando o número | 1h20–1h45 |
| Consolidação dos 20 blocos | `python3 scripts/executar_bloco.py --consolidar` | 1–5 min |

O mínimo por bloco é 70 minutos de carga. Restauração, início da API, conferências e exportação acrescentam tempo. Reserve duas horas por bloco; os 20 representam aproximadamente 27–35 horas, além das pausas e repetições de pares interrompidos. Os pilotos da paginação revisada foram aprovados. Execute o bloco 1 e confira seu pacote antes de deixar uma sequência longa.

## Iniciar e acompanhar

Para repetir a conferência do piloto 90/10, fora dos blocos:

```sh
python3 scripts/executar_bloco.py --piloto
```

Ele executa somente o par 90/10 com 500 usuários, repetição 4, nos dois modos e com a mesma semente, usando a navegação revisada. Usa os tempos e preparações completos, mas salva em pasta própria e não conta como execução dos blocos. O pacote fica em `results/campanha-paginacao-v3/piloto-capacidade.zip`; a execução de 30/10 já foi validada. Nenhuma carga é iniciada automaticamente pela instalação ou pela conferência.

O comando abre o terminal persistente `tcc-campanha-v3` e solicita SSH/sudo da geradora e as credenciais das três VMs de serviço. Aguarde a autenticação das três antes de se ausentar. As senhas não são gravadas; não há chave permanente nem sudo sem senha.

Um bloco mantém a sessão por até quatro horas. Na sequência, o limite é de duas horas por bloco solicitado, mais duas horas de margem, com mínimo de quatro horas. Não há nova autenticação entre blocos. A sequência para na primeira falha ou ao terminar o intervalo e encerra as sessões.

Mantenha ambos os computadores na energia, o cabo Ethernet e as quatro VMs em funcionamento, com a tampa do notebook aberta. O comando impede temporariamente a suspensão do notebook. No Windows, mantenha suspensão e reinicializações automáticas desativadas durante a execução. Evite outros trabalhos pesados e consultas manuais à API durante a medição.

Para fechar somente a visualização, pressione Ctrl+B e depois D. Para voltar:

```sh
tmux attach -t tcc-campanha-v3
```

Após a mensagem final, pressione Enter. As VMs podem ser desligadas entre blocos concluídos; preserve as configurações ao ligá-las novamente. Para interromper manualmente, pressione Ctrl+C e aguarde a exportação parcial.

## Resultados e retomada

Os pacotes são atualizados após cada par e ao encerrar o bloco, na geradora:

```text
/home/rhyan/tcc-runner-v3/results/campanha-paginacao-v3/exports/
```

Ao terminar o bloco ou a sequência, inclusive por falha, os pacotes disponíveis são copiados e conferidos por hash no notebook:

```text
results/campanha-paginacao-v3/bloco-01.zip
results/campanha-paginacao-v3/bloco-01.zip.sha256
...
results/campanha-paginacao-v3/bloco-20.zip
```

Na sequência, a cópia ocorre ao final para evitar disputa de rede/disco com a medição. Se a conexão impedir a cópia, os pacotes já salvos permanecem na geradora. Recupere um bloco sem executar carga novamente:

```sh
python3 scripts/executar_bloco.py --recolher 1
```

O piloto fica separado em `/home/rhyan/tcc-runner-v3/results/piloto-capacidade-v3/exports/piloto-capacidade.zip` e é copiado para a pasta local da campanha. Seu registro identifica a exclusão da consolidação. Os ZIPs de bloco contêm plano, manifesto, parâmetros, recibos, tentativas, resumos k6, dados brutos dos serviços e recursos da geradora/notebook, com inventário `SHA256.json`. Os resultados ficam fora do Git. Os pilotos de 30/10 já foram auditados; apresente o ZIP do primeiro bloco antes de avançar.

Nos blocos, para retomar após falha, repita o mesmo comando. Os pares completos desta campanha são preservados; os dois modos do par incompleto são repetidos em nova tentativa. Blocos posteriores não são iniciados após erro. Um bloco já completo somente reexporta o pacote. Blocos anteriores precisam estar completos para continuar.

Após os 20 blocos, `--consolidar` exige os 100 pares completos e seleciona somente a tentativa validada de cada par. Salva `summary.json`, `groups.csv` e `paired.csv` em `consolidacao.zip`, também copiado para o notebook. Um bloco isolado não fornece as cinco repetições de todos os cenários.

## Proteções e leitura dos erros

O protocolo 3 mantém a distinção entre saturação comprovadamente anterior à escrita de resultado incerto. O 503 identificado por `DATABASE_CAPACITY_EXCEEDED`, `operationApplied=false` e tipo `urn:tcc:problem:database-capacity` conta como erro/recusa e permite continuar. Timeout, 500, 503 genérico ou resposta de escrita fora do contrato interrompem a execução. Erros HTTP de leitura são medidos; HTTP 200 fora do contrato invalida o caso.

Os resumos separam tentativas, sucessos, recusas e falhas incertas, com vazão e latências de sucesso próprias. Recusas não são convertidas em sucesso. O [protocolo de paginação](PAGINACAO_V3.md) descreve a revisão; o [protocolo 2](EXPERIMENTO.md) registra o tratamento de falhas preservado.

Uma trava impede campanhas simultâneas. Antes de cada par são conferidos relógios, backup, imagem, índices, recursos, código e parâmetros. Mudanças durante a campanha são recusadas. As reservas são de 12 GiB no notebook, 2 GiB na geradora e 5 GiB na VM PostgreSQL; perder o acompanhamento do notebook interrompe o bloco. Não amplie volumes nem altere parâmetros para contornar uma falha: preserve o pacote e apresente o diagnóstico.
