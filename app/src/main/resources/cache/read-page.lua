if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return nil
end
return redis.call('GET', KEYS[2])
