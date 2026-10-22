# Ethernet experimental — 21/10/2026

Comunicação Ethernet configurada e validada: a tcc-load alcança a API em **`http://10.20.20.10:8080`**. Host e tcc-app alcançam o gerador por ping e SSH. Não foram executados testes de carga.

## Rede configurada

| Equipamento/interface | Endereço | Função |
| --- | --- | --- |
| Computador 1 — `br-tcc` | `10.20.20.1/24` | Bridge da Ethernet `enp4s0`, enlace de 1 Gbps |
| tcc-app — `enp7s0` | `10.20.20.10/24` | HTTP experimental, porta 8080 |
| Computador 2 — Ethernet | `10.20.20.2/24` | Endereço confirmado pelo usuário |
| tcc-load — `ens37` | `10.20.20.40/24` | Interface ativa e endereço confirmados pelo usuário |

A rede experimental não tem gateway ou DNS. O notebook mantém a internet em `wlo1`; a tcc-app mantém gateway e DNS em `enp1s0`, na rede privada. PostgreSQL e Redis permanecem em `10.10.10.20` e `10.10.10.30`. Wi-Fi e `tcc-network` foram preservados. Nenhuma regra manual de firewall foi acrescentada; Docker atualizou as regras das publicações.

## Persistência e cópias

| Componente | Configuração persistida |
| --- | --- |
| Bridge | Perfil `tcc-bridge`, UUID `cbc7c7ba-9820-46e5-9884-a95b308e4d6d` |
| Porta física | Perfil `tcc-ethernet-port`, UUID `06961784-0628-46d3-8caf-915df56a654a` |
| Perfil Ethernet anterior | UUID `6051479d-df65-3705-9f22-99be0f7f2e09`, preservado com conexão automática desativada |
| NetworkManager | Alterações persistidas em `/etc/netplan/90-NM-<UUID>.yaml`; novos perfis com conexão automática |
| Driver Ethernet do host | `r8169` somente no dispositivo PCI `0000:04:00.0`; `driverctl` persiste a escolha em `/etc/driverctl.d/pci-0000:04:00.0` |
| VM | NIC virtio MAC `52:54:00:20:20:10` na `br-tcc`, presente nos XMLs ativo e inativo |
| Netplan da VM | `/etc/netplan/60-tcc-experimental.yaml`, root:root, modo 600; [modelo versionado](tcc-app-experimental.netplan.yaml.example) com MAC e IP estático |
| Docker | [compose.ethernet.yaml](../app/compose.ethernet.yaml), mantendo a imagem e o modo de cache |

As cópias anteriores ficam no notebook em `/var/backups/tcc-ethernet-20261021` e na VM em `/home/rhyan/tcc-ethernet-20261021/antes`, em diretórios restritos ao root. Incluem configurações de rede, XMLs e regras de firewall; na VM, também os arquivos Compose. Não versione esses diretórios, pois podem conter credenciais. O arquivo `50-cloud-init.yaml` e a configuração Wi-Fi foram comparados com as cópias e permanecem iguais.

O novo Netplan foi gerado e aplicado somente à `enp7s0`, com `networkctl reload` e `networkctl reconfigure enp7s0`. Em 22/10, após nova inicialização do host e das VMs, bridge, driver, interfaces e acesso HTTP foram revalidados.

Inicialmente, o driver `r8168` 8.052.01 apresentava transmissão e interrupções praticamente paradas, sem resposta ARP dos equipamentos remotos; reassociá-lo não resolveu. A troca para o `r8169` do kernel restaurou imediatamente a comunicação. O pacote `driverctl` 0.115-1 persiste a escolha somente nessa placa, sem remover o driver anterior. Consulte o [manual do driverctl](https://manpages.debian.org/trixie/driverctl/driverctl.8.en.html).

## Operação e validação

Na tcc-app, preserve as três configurações ao administrar a aplicação com cache:

```sh
cd ~/tcc-app/infra/app
sudo docker compose -f compose.yaml -f compose.cache.yaml -f compose.ethernet.yaml ps
```

O mesmo conjunto deve acompanhar `up -d --no-build app`. Para operar sem cache mantendo Ethernet, use `compose.yaml` e `compose.ethernet.yaml`. A porta 8080 permanece publicada nos dois IPs da tcc-app; gerenciamento e métricas ficam somente em `127.0.0.1:8081` da VM.

No computador 1, os dois endereços HTTP retornaram 200 com conteúdo igual. Na tcc-app, as conexões privadas com PostgreSQL/Redis e o cache funcionaram, com falta seguida de acerto, sem fallback. HTTPS e rotas originais de internet foram preservados no host e nas VMs. As portas 5432, 6379 e 8081 foram recusadas em `10.20.20.10`, inclusive a partir da tcc-load.

Após a troca de driver, ARP confirmou o Windows em `10.20.20.2` e a tcc-load em `10.20.20.40`. A tcc-load respondeu ping e conexão TCP 22 com banner SSH. O Windows não respondeu ICMP, mas sua presença no enlace foi confirmada por ARP; não foi necessário liberar ping nesse host.

O GET executado por SSH na tcc-load retornou HTTP 200 e três pedidos da empresa 1. A rota do gerador usa `ens37`, com origem `10.20.20.40`; na tcc-app, a rota para o gerador usa `enp7s0`, com origem `10.20.20.10`. A internet da tcc-load permanece no NAT pela `ens33`, também validada por HTTPS. O caminho completo pela Ethernet está confirmado, sem pendências de comunicação. Os relatórios finais do host, da aplicação e do gerador ficam em `results/ethernet-20261021/`, ignorados pelo Git.

Para repetir o GET no PowerShell do computador 2:

```powershell
curl.exe -H "tenantId: 1" "http://10.20.20.10:8080/api/pedidos?page=0&size=20"
```

O ID 1 é da empresa mantida na validação anterior. O teste deve retornar 200, sem iniciar carga elevada.

## Reversão

Usar SSH pelo IP privado `10.10.10.10` e manter o Wi-Fi do notebook ativo. Os passos removem somente a rede experimental, preservando dados, imagem e cache da aplicação.

1. Na tcc-app, remover a publicação experimental, sem derrubar os demais serviços:

   ```sh
   cd ~/tcc-app/infra/app
   sudo docker compose -f compose.yaml -f compose.cache.yaml up -d --no-build app
   curl --fail http://127.0.0.1:8081/actuator/health
   ```

2. Na tcc-app, desativar somente a nova NIC e retirar seu arquivo de configuração. Preservar `50-cloud-init.yaml`; o destino abaixo deve estar livre:

   ```sh
   sudo networkctl down enp7s0
   sudo mv /etc/netplan/60-tcc-experimental.yaml /home/rhyan/tcc-ethernet-20261021/60-tcc-experimental.revertido.yaml
   sudo netplan generate
   sudo networkctl reload
   ```

3. No notebook, retirar somente a NIC adicional das configurações ativa e persistente da VM:

   ```sh
   sudo virsh -c qemu:///system detach-interface tcc-app bridge --mac 52:54:00:20:20:10 --live --config
   ```

   Se a VM estiver desligada, usar somente `--config`. Conferir os XMLs antes de repetir o comando; não redefinir todo o XML da VM.

4. No notebook, remover somente os dois perfis criados e restaurar a conexão automática do perfil anterior:

   ```sh
   sudo nmcli connection down tcc-ethernet-port
   sudo nmcli connection down tcc-bridge
   sudo nmcli connection delete tcc-ethernet-port
   sudo nmcli connection delete tcc-bridge
   sudo nmcli connection modify 6051479d-df65-3705-9f22-99be0f7f2e09 connection.autoconnect yes
   ```

   Conferir os arquivos gerenciados em `/etc/netplan/90-NM-<UUID>.yaml`. Não restaurar indiscriminadamente toda a pasta Netplan ou o conjunto de regras de firewall. A Ethernet anterior usava DHCP; não precisa receber endereço nesse enlace após a reversão.

5. Opcionalmente, para desfazer também a escolha do driver, após retirar a rede experimental:

   ```sh
   sudo driverctl unset-override 0000:04:00.0
   ```

   Essa etapa pode devolver o dispositivo ao `r8168` que apresentou a falha. Não é necessária para retirar a bridge; o pacote e o driver anterior foram preservados.

Não há regras manuais de firewall desta intervenção a remover; Docker atualiza suas publicações ao recriar a aplicação. Ao concluir, reconferir Wi-Fi, acesso privado à VM, HTTP em `10.10.10.10:8080` e saúde local da aplicação. Preservar as cópias e registrar a reversão.
