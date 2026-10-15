#!/bin/sh
set -eu

administrator_password=$(cat /run/secrets/redis_password)

if [ "${#administrator_password}" -lt 32 ]; then
  echo 'A senha Redis deve conter pelo menos 32 caracteres.' >&2
  exit 1
fi

administrator_password_hash=$(printf '%s' "$administrator_password" | sha256sum)
administrator_password_hash=${administrator_password_hash%% *}
printf 'user default on #%s ~* &* +@all\n' "$administrator_password_hash" > /tmp/tcc-users.acl

if [ -f /run/secrets/redis_app_password ]; then
  application_password=$(cat /run/secrets/redis_app_password)

  if [ "${#application_password}" -lt 32 ] || [ "$application_password" = "$administrator_password" ]; then
    echo 'A senha Redis da aplicação deve ter ao menos 32 caracteres e diferir da administrativa.' >&2
    exit 1
  fi

  application_password_hash=$(printf '%s' "$application_password" | sha256sum)
  application_password_hash=${application_password_hash%% *}
  printf 'user app on #%s ~tcc:* +@connection +get +set +eval +evalsha\n' "$application_password_hash" >> /tmp/tcc-users.acl
  unset application_password application_password_hash
fi

chmod 644 /tmp/tcc-users.acl
unset administrator_password administrator_password_hash

exec /usr/local/bin/docker-entrypoint.sh redis-server /usr/local/etc/redis/redis.conf
