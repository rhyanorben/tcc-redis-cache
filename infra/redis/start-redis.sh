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
# O usuário da aplicação é opcional e só existe com a sobreposição de secrets.
if [ -f /run/secrets/redis_app_password ]; then
  app_password=$(cat /run/secrets/redis_app_password)
  if [ "${#app_password}" -lt 32 ] || [ "$app_password" = "$password" ]; then
    echo 'A senha Redis da aplicação deve ter ao menos 32 caracteres e diferir da administrativa.' >&2
    exit 1
  fi
  app_hash=$(printf '%s' "$app_password" | sha256sum)
  app_hash=${app_hash%% *}
  printf 'user app on #%s ~tcc:* +@connection +get +set +eval +evalsha\n' "$app_hash" >> /tmp/tcc-users.acl
  unset app_password app_hash
fi
chmod 644 /tmp/tcc-users.acl
unset password hash
exec /usr/local/bin/docker-entrypoint.sh redis-server /usr/local/etc/redis/redis.conf
