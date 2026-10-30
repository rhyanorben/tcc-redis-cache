#!/usr/bin/env python3
import argparse
import subprocess
import tarfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE_FOLDERS = ('load/', 'monitoring/', 'infra/experiment/', 'scripts/')
DOCUMENTS = ('README.md', 'docs/PAGINACAO_V3.md', 'docs/CAMPANHA_EM_BLOCOS.md', 'docs/VALIDACAO_PAGINACAO_V3.md')


def build_package(project, destination):
    names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=project
    ).decode().split('\0')
    files = []
    for name in sorted(set(names)):
        if not name or not (name.startswith(SOURCE_FOLDERS) or name in DOCUMENTS):
            continue
        path = project / name
        if path.is_symlink():
            raise ValueError('Link simbólico não permitido no pacote: ' + name)
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.suffix not in ('.py', '.js', '.json', '.sql', '.md') and not name.startswith('load/hooks.vm/'):
            continue
        files.append((path, name))
    required = {'load/experiment.js', 'load/navigation.js', 'load/navigation.json', 'load/campanha.json'}
    if not required.issubset({name for path, name in files}):
        raise ValueError('O código da paginação v3 está incompleto.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, 'x:gz') as archive:
        for path, name in files:
            archive.add(path, arcname=name, recursive=False)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description='Empacota o código local da paginação v3, sem acessar VMs ou executar carga.')
    parser.add_argument('--saida', type=Path, required=True)
    arguments = parser.parse_args()
    count = build_package(PROJECT, arguments.saida)
    print(f'Pacote criado: {arguments.saida}; {count} arquivos. Nenhum ensaio iniciado.')


if __name__ == '__main__':
    main()
