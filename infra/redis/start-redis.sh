#!/bin/sh
set -eu
# O arquivo gerado contém somente o hash; a senha não vai nos argumentos.
password=$(cat /run/secrets/redis_password)
if [ "${#password}" -lt 32 ]; then
  echo 'A senha Redis deve conter pelo menos 32 caracteres.' >&2
  exit 1
fi
hash=$(printf '%s' "$password" | sha256sum)
hash=${hash%% *}
printf 'user default on #%s ~* &* +@all\n' "$hash" > /tmp/tcc-users.acl
chmod 644 /tmp/tcc-users.acl
unset password hash
exec /usr/local/bin/docker-entrypoint.sh redis-server /usr/local/etc/redis/redis.conf
