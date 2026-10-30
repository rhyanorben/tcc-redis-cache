import math


SUCCESS_LATENCY_PREFIXES = ('read_success_latency_ms.', 'write_success_latency_ms.')
COUNTERS = (
    'reads', 'writes', 'requests', 'errors', 'read_errors', 'write_errors',
    'read_attempts', 'write_attempts', 'attempts', 'read_successes', 'write_successes',
    'successes', 'read_rejections', 'write_rejections', 'rejections', 'write_uncertain',
    'response_contract_errors',
)


def validate_outcomes(summary):
    if summary.get('schema_version') != 2 or summary.get('protocol_version') != 2:
        raise ValueError('Resumo exige schema e protocolo 2; não misture campanhas anteriores.')
    for name in COUNTERS:
        value = summary.get(name)
        if type(value) is not int or value < 0:
            raise ValueError(f'Contador ausente ou inválido: {name}.')
    equalities = (
        ('read_attempts', summary['reads']),
        ('write_attempts', summary['writes']),
        ('attempts', summary['requests']),
        ('requests', summary['reads'] + summary['writes']),
        ('errors', summary['read_errors'] + summary['write_errors']),
        ('successes', summary['read_successes'] + summary['write_successes']),
        ('reads', summary['read_successes'] + summary['read_errors']),
        ('writes', summary['write_successes'] + summary['write_errors']),
        ('write_errors', summary['write_rejections'] + summary['write_uncertain']),
        ('rejections', summary['read_rejections'] + summary['write_rejections']),
    )
    for name, expected in equalities:
        if summary[name] != expected:
            raise ValueError(f'Contadores incompatíveis: {name}.')
    if summary['read_rejections'] > summary['read_errors']:
        raise ValueError('Recusas de leitura excedem os erros de leitura.')
    if summary['write_uncertain'] != 0 or summary['response_contract_errors'] != 0:
        raise ValueError('Falha incerta ou violação de contrato impede consolidar a execução.')
    seconds = summary.get('nominal_measurement_seconds')
    if seconds != 300:
        raise ValueError('Protocolo 2 exige medição de 300 segundos.')
    rates = {
        'throughput_requests_per_second': summary['requests'] / seconds,
        'successful_requests_per_second': summary['successes'] / seconds,
        'successful_read_requests_per_second': summary['read_successes'] / seconds,
        'successful_write_requests_per_second': summary['write_successes'] / seconds,
        'error_ratio': summary['errors'] / summary['requests'] if summary['requests'] else None,
        'observed_write_ratio': summary['writes'] / summary['requests'] if summary['requests'] else None,
    }
    if summary['requests'] <= 0:
        raise ValueError('Medição sem tentativas não compõe a campanha.')
    for name, expected in rates.items():
        value = summary.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError(f'Taxa incompatível com os contadores: {name}.')
    for name, count in (
            ('read_latency_ms', summary['reads']), ('write_latency_ms', summary['writes']),
            ('read_success_latency_ms', summary['read_successes']),
            ('write_success_latency_ms', summary['write_successes'])):
        values = summary.get(name)
        if count == 0:
            if values is not None:
                raise ValueError(f'Latência sem requisições correspondentes: {name}.')
            continue
        required = {'avg', 'min', 'med', 'max', 'p(95)', 'p(99)'}
        if not isinstance(values, dict) or not required.issubset(values):
            raise ValueError(f'Latência ausente ou incompleta: {name}.')
        if any(type(values[key]) not in (int, float) or not math.isfinite(values[key]) or values[key] < 0 for key in required):
            raise ValueError(f'Latência inválida: {name}.')
