"""Read retained component evidence without recreating the generating environment."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import component_display as c

with tempfile.TemporaryDirectory(prefix='component_retirement_') as temporary:
    root=Path(temporary); formal=root/'formal'; process=root/'process'
    folder=process/'component_updates'/'retained'; prior=process/'prior'
    formal.mkdir(); folder.mkdir(parents=True);prior.mkdir()
    write=lambda p,v:p.write_text(json.dumps(v),encoding='utf-8')
    names=['raw_data.csv','define.R','note.md','x_detail.html','analysis_db_x.xlsx',
           'analysis_codebook_x.xlsx','db_x.xlsx','codebook_x.xlsx']
    for name in names:
        (formal/name).write_text('original '+name,encoding='utf-8')
        shutil.copy2(formal/name,folder/name)
    hashes={p.name:c.sha(p) for p in formal.iterdir()}
    history={}
    for name in ('definition_search_record.json','website_sync_result.json'):
        write(process/name,{'retained':True});shutil.copy2(process/name,folder/name)
        history[name]=c.sha(process/name)
    proof=prior/'definition_metadata_update.json';write(proof,{'candidate_hashes':hashes})
    baseline=dict(scope='component_display',formal=str(formal),topic='001',note='note.md',r='define.R',detail='x_detail.html',
                  four={name:hashes[name] for name in names if name.endswith('.xlsx')},history=history,
                  hashes=hashes,proof_files={str(proof):c.sha(proof)},proof_formal=str(prior),proof_process=str(prior),
                  tools={'SKILL.md':'A'*64,'dbCodeBookr':{'NEWS.md':'B'*64}},
                  config=str(root/'no-longer-installed.json'),config_hash='C'*64)
    bp=folder/'baseline.json';write(bp,baseline)
    for name in ('define.R','note.md','x_detail.html'):
        (formal/name).write_text('verified candidate '+name,encoding='utf-8')
    evidence=process/'generation.json';write(evidence,{'retained_ast_and_generation':'synthetic evidence'})
    receipt=dict(status='verified',baseline=str(bp),baseline_hash=c.sha(bp),
                 files={p.name:c.sha(p) for p in formal.iterdir()},evidence={str(evidence):c.sha(evidence)})
    write(process/c.MARKER,receipt)
    snapshot=lambda:{str(p.relative_to(root)):c.sha(p) for p in root.rglob('*') if p.is_file()}
    assert not (ROOT/'scripts/update_reader_copy.py').exists()
    assert not hasattr(c,'prepare') and not hasattr(c,'run') and not hasattr(c,'tools')
    # The predecessor's semantic checks are covered by legacy-delivery tests.
    # Exercise component bindings without inventing a real R execution.
    with patch('legacy_delivery_checks.verify_metadata_update',return_value={'ok':True}) as predecessor, \
         patch('subprocess.run',side_effect=AssertionError('Historical verification launched a process')):
        original=snapshot()
        result=c.verify(formal,process,'001')
        assert result['result_check']['historical_validation']=='PRESERVED_NOT_REVALIDATED'
        predecessor.assert_called_once_with(prior,prior,'001')
        assert snapshot()==original
        for target in (bp,proof,process/'definition_search_record.json',process/'website_sync_result.json',
                       formal/'raw_data.csv',formal/'note.md',formal/'analysis_db_x.xlsx',evidence):
            saved=target.read_bytes();target.write_bytes(saved+b' changed')
            observed=snapshot()
            try:c.verify(formal,process,'001')
            except ValueError:pass
            else:raise AssertionError('Changed historical proof accepted: '+str(target))
            assert snapshot()==observed
            target.write_bytes(saved)
        predecessor.side_effect=ValueError('predecessor validation failed')
        try:c.verify(formal,process,'001')
        except ValueError as error:assert 'predecessor' in str(error)
        else:raise AssertionError('Failed predecessor verification bypassed')
print('COMPONENT_RETIREMENT_PASS: no runtime discovery or writes; historical source/artifacts/evidence and predecessor bindings retained')
