"""Synthetic file-level checks, not CHNS real-download or business acceptance."""
import csv
import sys
import tempfile
import zipfile
import json
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from chns_export_contract import normalize_year, validate_person_package
from recover_dbcodebook_export import inspect_archive
from check_definition_output import check_identity_values


def write(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        csv.writer(handle).writerows(rows)


def rejected(fn, text):
    try:
        fn()
    except ValueError as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError('Invalid package accepted')


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dictionary = [['Variable', 'newname', 'File type'],
                      ['age (rst_12)', 'age', 'uniqID'],
                      ['sex (mast_pub_12)', 'sex', 'personID']]
        write(root / 'raw_codebook.csv', dictionary)
        header = ['ID', 'IDind', 'WAVE', 'hhid (rst_12)', 'age']
        values = [['opaque-a', '001', '1989', '002', '30'],
                  ['opaque-b', '001', '1991', '003', '32']]
        write(root / 'raw_data.csv', [header, *values])
        write(root / 'raw_data_mast_pub_12.csv', [['IDind', 'sex'], ['001', 'Female']])
        members = ['raw_data.csv', 'raw_data_mast_pub_12.csv']
        check = lambda: validate_person_package(root, members, ['age', 'sex'])
        assert check()['raw_data.csv']['rows'] == 2
        archive = root / 'synthetic.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            for name in [*members, 'raw_codebook.csv']:
                output.write(root / name, name)
        assert inspect_archive(archive, ['age', 'sex'], 'chns')['data']['raw_data.csv']['rows'] == 2
        assert (root / members[1]).read_text(encoding='utf-8-sig').splitlines()[1].startswith('001,')
        # Exercise the actual output checker dispatch: sex is intentionally absent from main raw.
        report = root / 'checker.json'
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/check_definition_output.py'),
            '--formal-dir', str(root), '--db', 'chns', '--raw-vars', 'age,sex', '--report', str(report)],
            capture_output=True, text=True, encoding='utf-8')
        checks = json.loads(report.read_text(encoding='utf-8'))['checks']
        for name in ['CHNS personal/static file contract', 'raw_data header', 'raw_codebook vars']:
            assert any(item['check'] == name and item['ok'] for item in checks), (name, checks, result.stderr)
        analysis_header = ['ID', 'IDind', 'WAVE', 'defined_sex']
        analysis = [analysis_header, ['opaque-a', '001', 1989, 'Female'], ['opaque-b', '001', 1991, 'Female']]
        identity_checks = []
        check_identity_values(root / 'raw_data.csv', header, analysis, analysis_header, identity_checks, 'chns')
        assert all(item['ok'] for item in identity_checks), identity_checks
        analysis[1][1] = 1
        identity_checks = []
        check_identity_values(root / 'raw_data.csv', header, analysis, analysis_header, identity_checks, 'chns')
        assert any(not item['ok'] for item in identity_checks), identity_checks
        # Actual CHNS CSV export displays integral WAVE values with .0; keep IDs untouched.
        decimal_values = [['opaque-a', '001.0', '1989.0', '002', '30'],
                          ['opaque-b', '001.0', '1991.00', '003', '32']]
        write(root / 'raw_data.csv', [header, *decimal_values])
        write(root / members[1], [['IDind', 'sex'], ['001.0', 'Female']])
        assert check()['raw_data.csv']['rows'] == 2
        analysis = [analysis_header, ['opaque-a', '001.0', 1989, 'Female'], ['opaque-b', '001.0', 1991, 'Female']]
        identity_checks = []
        check_identity_values(root / 'raw_data.csv', header, analysis, analysis_header, identity_checks, 'chns')
        assert all(item['ok'] for item in identity_checks), identity_checks
        assert normalize_year('1989.000') == '1989'
        for value in ['1989.5', '1989.1', '1989e0', '1989.0x', '2020.0']:
            rejected(lambda: normalize_year(value), 'invalid year')
        write(root / 'raw_data.csv', [header, decimal_values[0], ['different', '001.0', '1989', '002', '30']])
        rejected(check, 'duplicate person-period')
        write(root / members[1], [['IDind', 'sex'], ['001', 'Female']])
        write(root / 'raw_data.csv', [[*header, 'sex'], [*values[0], 'Female'], [*values[1], 'Female']])
        rejected(check, 'business columns differ')
        write(root / 'raw_data.csv', [header, values[0], ['different', *values[0][1:]]])
        rejected(check, 'duplicate person-period')
        write(root / 'raw_data.csv', [header, *values])
        write(root / members[1], [['IDind', 'sex'], ['001', 'Female'], ['001', 'Male']])
        rejected(check, 'duplicate personal identity')
        write(root / members[1], [['IDind', 'sex'], ['001', 'Female']])
        dictionary[2][2] = 'relationID'
        write(root / 'raw_codebook.csv', dictionary)
        rejected(check, 'record level')
    print('CHNS personal/static file and output-checker fixtures PASS; real package and full generation untested')


if __name__ == '__main__':
    main()
