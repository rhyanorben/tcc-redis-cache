local generation = redis.call('GET', KEYS[1])

if not generation then
    generation = ARGV[1]
    redis.call('SET', KEYS[1], generation)
end

return generation
