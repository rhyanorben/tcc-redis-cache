import math

from planejar import NAVIGATION


SUCCESS_LATENCY_PREFIXES = ('read_success_latency_ms.', 'write_success_latency_ms.')
COUNTERS = (
    'reads', 'writes', 'requests', 'errors', 'read_errors', 'write_errors',
    'read_attempts', 'write_attempts', 'attempts', 'read_successes', 'write_successes',
    'successes', 'read_rejections', 'write_rejections', 'rejections', 'write_uncertain',
    'response_contract_errors',
)


def validate_outcomes(summary):
    if summary.get('schema_version') != 2 or summary.get('protocol_version') not in (2, 3):
        raise ValueError('Resumo exige schema 2 e protocolo 2 ou 3; não misture campanhas.')
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
        raise ValueError('A campanha exige medição de 300 segundos.')
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
    if summary['protocol_version'] == 3:
        validate_navigation(summary)


def validate_navigation(summary):
    navigation = summary.get('navigation')
    if not isinstance(navigation, dict) or navigation.get('config') != NAVIGATION:
        raise ValueError('Navegação ausente ou divergente do protocolo 3.')
    for name in ('forward_visits', 'reverse_visits'):
        if type(navigation.get(name)) is not int or navigation[name] < 0:
            raise ValueError(f'Contador de visitas inválido: {name}.')
    visits = navigation['forward_visits'] + navigation['reverse_visits']
    if summary['reads'] > 0 and visits == 0:
        raise ValueError('Leituras sem visitas registradas.')
    for name, total in (('reads', summary['reads']), ('errors', summary['read_errors'])):
        values = navigation.get(name)
        if not isinstance(values, dict) or set(values) != {'first', 'intermediate', 'last'}:
            raise ValueError(f'Classes de páginas ausentes: {name}.')
        if any(type(value) is not int or value < 0 for value in values.values()) or sum(values.values()) != total:
            raise ValueError(f'Contadores por classe de página incompatíveis: {name}.')
    if visits > navigation['reads']['first']:
        raise ValueError('Toda visita precisa iniciar com uma leitura da primeira página.')
    for name in ('first', 'intermediate', 'last'):
        if navigation['errors'][name] > navigation['reads'][name]:
            raise ValueError('Erros de páginas excedem as leituras.')
        values = navigation.get('latency_ms', {}).get(name)
        if navigation['reads'][name] == 0:
            if values is not None:
                raise ValueError('Latência por página sem leituras correspondentes.')
        elif not isinstance(values, dict) or any(
                type(values.get(key)) not in (int, float) or not math.isfinite(values[key]) or values[key] < 0
                for key in ('avg', 'min', 'med', 'max', 'p(95)', 'p(99)')):
            raise ValueError('Latência por classe de página ausente ou inválida.')
