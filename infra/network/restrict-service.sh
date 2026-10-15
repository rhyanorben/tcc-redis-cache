#!/bin/sh
# Executar como root após Docker, em cada VM de dados.
set -eu
case "${1:-}" in
  postgres) ip=10.10.10.20; port=5432 ;;
  redis) ip=10.10.10.30; port=6379 ;;
  *) echo 'Uso: restrict-service.sh postgres|redis' >&2; exit 2 ;;
esac
# Filtra só conexões encaminhadas para a porta publicada deste serviço.
# Não modifica SSH, INPUT ou outras regras existentes.
iptables -w -nL DOCKER-USER >/dev/null
if ! iptables -w -C DOCKER-USER -p tcp ! -s 10.10.10.10/32 -m conntrack --ctdir ORIGINAL --ctorigdst "$ip" --ctorigdstport "$port" -j DROP 2>/dev/null; then
  iptables -w -I DOCKER-USER 1 -p tcp ! -s 10.10.10.10/32 -m conntrack --ctdir ORIGINAL --ctorigdst "$ip" --ctorigdstport "$port" -j DROP
fi
