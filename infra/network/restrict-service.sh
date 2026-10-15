#!/bin/sh
set -eu

case "${1:-}" in
  postgres)
    service_ip=10.10.10.20
    service_port=5432
    ;;
  redis)
    service_ip=10.10.10.30
    service_port=6379
    ;;
  *)
    echo 'Uso: restrict-service.sh postgres|redis' >&2
    exit 2
    ;;
esac

iptables -w -nL DOCKER-USER >/dev/null

if ! iptables -w -C DOCKER-USER -p tcp ! -s 10.10.10.10/32 \
    -m conntrack --ctdir ORIGINAL --ctorigdst "$service_ip" \
    --ctorigdstport "$service_port" -j DROP 2>/dev/null; then
  iptables -w -I DOCKER-USER 1 -p tcp ! -s 10.10.10.10/32 \
    -m conntrack --ctdir ORIGINAL --ctorigdst "$service_ip" \
    --ctorigdstport "$service_port" -j DROP
fi
