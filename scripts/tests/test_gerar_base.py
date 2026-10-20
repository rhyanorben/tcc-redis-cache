import importlib.util
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'gerar_base.py'
MODULE_SPEC = importlib.util.spec_from_file_location('gerar_base', SCRIPT_PATH)
SEED_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(SEED_MODULE)


class GerarBaseTest(unittest.TestCase):
    def arguments(self, **overrides):
        values = {
            'empresas': 2,
            'clientes_por_empresa': 5,
            'pedidos_por_empresa': 7,
            'itens_por_pedido': 3,
            'lote': 'teste-001',
        }
        values.update(overrides)
        return Namespace(**values)

    def run_generator(self, output_path, *extra_arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), '--empresas', '2',
             '--pedidos-por-empresa', '7', '--saida', str(output_path), *extra_arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_three_items_and_total_thirty(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'base.sql'
            result = self.run_generator(output_path)
            self.assertEqual(0, result.returncode, result.stderr)
            sql = output_path.read_text(encoding='utf-8')

        self.assertIn('SELECT e.id, c.id, 30.00,', sql)
        self.assertIn('generate_series(1, 3) n;', sql)
        self.assertIn('78 registros previstos', result.stdout)
        self.assertIn('Nenhuma conexão ou alteração no banco', result.stdout)

    def test_item_count_override_adjusts_total_and_expected_count(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'base.sql'
            result = self.run_generator(output_path, '--itens-por-pedido', '5')
            self.assertEqual(0, result.returncode, result.stderr)
            sql = output_path.read_text(encoding='utf-8')

        self.assertIn('SELECT e.id, c.id, 50.00,', sql)
        self.assertIn('generate_series(1, 5) n;', sql)
        self.assertIn('106 registros previstos', result.stdout)

    def test_rejects_nonpositive_and_noninteger_sizes(self):
        for option in ('--empresas', '--clientes-por-empresa',
                       '--pedidos-por-empresa', '--itens-por-pedido'):
            for value in ('0', '-1', '1.5', 'abc'):
                with self.subTest(option=option, value=value):
                    with tempfile.TemporaryDirectory() as temporary_directory:
                        output_path = Path(temporary_directory) / 'base.sql'
                        result = self.run_generator(output_path, option, value)
                        self.assertNotEqual(0, result.returncode)
                        self.assertFalse(output_path.exists())

    def test_rejects_invalid_batch_identifier(self):
        for batch in ('', "x'; DROP TABLE empresa;", 'a b', 'x' * 41):
            with self.subTest(batch=batch):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    output_path = Path(temporary_directory) / 'base.sql'
                    result = self.run_generator(output_path, '--lote', batch)
                    self.assertNotEqual(0, result.returncode)
                    self.assertFalse(output_path.exists())

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'base.sql'
            output_path.write_text('arquivo existente', encoding='utf-8')
            result = self.run_generator(output_path)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual('arquivo existente', output_path.read_text(encoding='utf-8'))

    def test_output_is_reproducible(self):
        first_sql = SEED_MODULE.build_seed_sql(self.arguments())
        second_sql = SEED_MODULE.build_seed_sql(self.arguments())
        self.assertEqual(first_sql, second_sql)
        self.assertNotIn('now()', first_sql)

    def test_validates_counts_and_totals_before_commit(self):
        sql = SEED_MODULE.build_seed_sql(self.arguments())
        self.assertLess(sql.index('Contagens ou totais divergentes por empresa.'), sql.index('COMMIT;'))
        self.assertLess(sql.index('Quantidade de itens ou total divergente por pedido.'), sql.index('COMMIT;'))
        self.assertIn('coalesce(i.quantidade, 0) <> 21', sql)
        self.assertIn('coalesce(p.total, 0) <> 210.00', sql)
        self.assertIn('coalesce(i.total, 0) <> p.total', sql)
        self.assertTrue(sql.startswith('\\set ON_ERROR_STOP on\nBEGIN;'))

    def test_refuses_duplicate_batch_before_inserts(self):
        sql = SEED_MODULE.build_seed_sql(self.arguments())
        self.assertIn("starts_with(nome, 'TCC-teste-001 Empresa ')", sql)
        self.assertLess(sql.index('pg_advisory_xact_lock'), sql.index('Lote já existe'))
        self.assertLess(sql.index('Lote já existe'), sql.index('INSERT INTO empresa'))
        self.assertNotIn('DELETE FROM', sql)
        self.assertNotIn('TRUNCATE', sql)

    def test_full_experimental_dataset_count(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'base.sql'
            result = self.run_generator(
                output_path, '--empresas', '100', '--clientes-por-empresa', '5000',
                '--pedidos-por-empresa', '20000',
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('8,500,100 registros previstos', result.stdout)
            self.assertLess(output_path.stat().st_size, 20000)


if __name__ == '__main__':
    unittest.main()
