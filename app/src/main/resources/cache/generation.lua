local version = redis.call('GET', KEYS[1])
if not version then
    version = ARGV[1]
    redis.call('SET', KEYS[1], version)
end
return version
