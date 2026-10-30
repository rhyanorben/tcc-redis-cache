import argparse
import re


def parse_blocks(value):
    match = re.fullmatch(r'([1-9]|1[0-9]|20)-([1-9]|1[0-9]|20)', value)
    if not match:
        raise argparse.ArgumentTypeError('Informe um intervalo como 2-5, entre 1 e 20')
    first, last = map(int, match.groups())
    if first > last:
        raise argparse.ArgumentTypeError('O bloco inicial deve ser menor ou igual ao final')
    return list(range(first, last + 1))
