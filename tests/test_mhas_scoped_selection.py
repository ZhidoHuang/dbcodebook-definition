import copy
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_source_selection import build_record_action, browser_code


class ScopedTests(unittest.TestCase):
    def record(self):
        return {'database': 'MHAS', 'status': 'READY', 'source_groups': [
            {'raw_variables': ['early', 'late_2003', 'late_2012'],
             'source_identities': ['c60 (Core)', 'c60 (Core)', 'c60_12 (Core)']}],
            'mhas_selection': {'dictionary_sha256': 'a'*64, 'inputs': [
                {'variable_id': 'current_Core', 'file': 'Core', 'aliases': {'c60': 'early'},
                 'available_periods': ['2001'], 'period_bindings': {'2001': 'c60'}},
                {'variable_id': 'cage_Core', 'file': 'Core', 'aliases': {'c60': 'late_2003', 'c60_12': 'late_2012'},
                 'available_periods': ['2003', '2012'],
                 'period_bindings': {'2003': 'c60', '2012': 'c60_12'}}]}}

    def test_same_raw_name_keeps_different_identity_and_period(self):
        action = build_record_action(self.record(), 'http://fixture/home/mhas/')
        self.assertEqual(len(action['selected']), 3)
        self.assertNotEqual(action['selected'][0]['variable_id'], action['selected'][1]['variable_id'])
        self.assertEqual(action['aliases'], ['early', 'late_2003', 'late_2012'])
        self.assertIn('dictionary_sha256', browser_code(action, 'select'))

    def test_tampered_action_rejected(self):
        action = build_record_action(self.record(), 'http://fixture/home/mhas/')
        action['selected'][0]['periods'] = ['2003']
        with self.assertRaises(ValueError): browser_code(action, 'select')

    def test_implicit_extra_period_rejected(self):
        record = self.record()
        record['mhas_selection']['inputs'][0]['available_periods'].append('2003')
        with self.assertRaises(ValueError): build_record_action(record, 'http://fixture/')

    def test_duplicate_expanded_alias_rejected(self):
        record = self.record()
        record['mhas_selection']['inputs'][0]['aliases']['c60'] = 'late_2003'
        with self.assertRaises(ValueError): build_record_action(record, 'http://fixture/')

    def test_legacy_unchanged(self):
        record = {'database': 'MHAS', 'status': 'READY', 'source_groups': [
            {'raw_variables': ['age'], 'source_identities': ['age (Core)']}]}
        self.assertEqual(build_record_action(record, 'http://fixture/')['kind'], 'source_selection_v1')

    def test_repeated_column_is_one_alias_with_all_periods(self):
        record = self.record()
        record['mhas_selection']['inputs'] = [{
            'variable_id': 'pc62_Core', 'file': 'Core',
            'aliases': {'pc62': 'proxy_excess'},
            'available_periods': ['2001', '2003'],
            'period_bindings': {'2001': 'pc62', '2003': 'pc62'}}]
        record['source_groups'] = [{'raw_variables': ['proxy_excess'],
                                    'source_identities': ['pc62 (Core)']}]
        action = build_record_action(record, 'http://fixture/')
        self.assertEqual(action['aliases'], ['proxy_excess'])
        self.assertEqual(action['selected'][0]['periods'], ['2001', '2003'])
        self.assertEqual(action['input_text'], 'pc62_Core (Core)=proxy_excess')
        self.assertEqual(action['source_cell_count'], 2)

    def test_old_automatic_names_require_migration(self):
        record = self.record()
        record['mhas_selection']['inputs'][0].pop('aliases')
        record['mhas_selection']['inputs'][0]['alias'] = 'early'
        with self.assertRaisesRegex(ValueError, 'obsolete'):
            build_record_action(record, 'http://fixture/')

    def test_continuation_is_bounded(self):
        action = build_record_action(self.record(), 'http://fixture/')
        action['rename_offset'] = 1
        self.assertIn('rename', browser_code(action, 'select'))
        action['rename_offset'] = len(action['selected'])
        with self.assertRaises(ValueError): browser_code(action, 'select')

    def test_partial_scope_keeps_available_evidence_without_exporting_other_period(self):
        record = self.record()
        item = record['mhas_selection']['inputs'][0]
        item['available_periods'] = ['2001', '2003']
        item['available_bindings'] = {'2001': 'c60', '2003': 'c60'}
        action = build_record_action(record, 'http://fixture/')
        self.assertEqual(action['selected'][0]['periods'], ['2001'])
        self.assertEqual(action['initial'][0]['periods'], ['2001', '2003'])
        self.assertIn('MHAS_PERIOD_CELL_NOT_VISIBLE', browser_code(action, 'select'))
        item['period_bindings']['2003'] = 'wrong'
        with self.assertRaises(ValueError): build_record_action(record, 'http://fixture/')

    def test_one_physical_column_can_keep_period_specific_business_aliases(self):
        record = self.record()
        record['mhas_selection']['inputs'] = [{
            'variable_id': 'c60_Core', 'file': 'Core', 'aliases': {'c60': 'current'},
            'period_aliases': {'2003': 'cut'},
            'available_periods': ['2001', '2003'],
            'period_bindings': {'2001': 'c60', '2003': 'c60'}}]
        record['source_groups'] = [{'raw_variables': ['current', 'cut'],
                                    'source_identities': ['c60 (Core)', 'c60 (Core)']}]
        action = build_record_action(record, 'http://fixture/')
        self.assertEqual(action['aliases'], ['current', 'cut'])
        self.assertEqual([r['periods'] for r in action['selected']], [['2001'], ['2003']])

    def test_resume_keeps_settled_scope_and_rejects_false_marker(self):
        action = build_record_action(self.record(), 'http://fixture/')
        action['selection_resume'] = True
        self.assertIn('selection_resume', browser_code(action, 'select'))
        action['selection_resume'] = False
        with self.assertRaises(ValueError): browser_code(action, 'select')

    def test_export_order_retains_complete_tags_before_appended_period_cells(self):
        record = self.record()
        item = record['mhas_selection']['inputs'][0]
        item['available_periods'] = ['2001', '2003']
        item['available_bindings'] = {'2001': 'c60', '2003': 'c60'}
        action = build_record_action(record, 'http://fixture/')
        self.assertEqual(action['aliases'], ['late_2003', 'late_2012', 'early'])
        self.assertEqual(action['selected'][0]['periods'], ['2001'])

    def test_new_tag_edit_guard_is_observed_before_rename(self):
        columns = ['q'+str(i) for i in range(6)]
        periods = [str(2001+i) for i in range(6)]
        record = {'database':'MHAS','status':'READY',
            'source_groups':[{'raw_variables':['out'+str(i) for i in range(6)],
                              'source_identities':[c+' (Core)' for c in columns]}],
            'mhas_selection':{'dictionary_sha256':'a'*64,'inputs':[{
                'variable_id':'series_Core','file':'Core',
                'aliases':{c:'out'+str(i) for i,c in enumerate(columns)},
                'available_periods':periods,'period_bindings':dict(zip(periods,columns))}]}}
        action = build_record_action(record, 'http://fixture/')
        action['rename_offset'] = 0
        fixture = r'''
const assert = require('node:assert/strict');
const run = ACTION;
const nodes = ROWS.map((r,i)=>({r:{...r,alias:r.initial_alias},guard:true,
  get dataset(){return {identity:this.r.variable_id,variable:this.r.variable,display:this.r.alias,periods:JSON.stringify(this.r.periods),dictionarySha256:this.r.dictionary_sha256};},
  getAttribute(k){return ({'data-identity':this.r.variable_id,'data-variable':this.r.variable,
    'data-display':this.r.alias,'data-periods':JSON.stringify(this.r.periods),
    'data-file':this.r.file,'data-dictionary-sha256':this.r.dictionary_sha256})[k];},
  hasAttribute(k){return k==='data-just-added' && this.guard;},
  classList:{contains:()=>false},querySelector(){return {textContent:this.r.alias};}}));
const find = selector => nodes.find(n=>selector.includes('data-identity="'+n.r.variable_id+'"') && selector.includes('data-variable="'+n.r.variable+'"'));
global.document={querySelector:find};
let guards=0;
function locator(selector){const node=find(selector);return {
 count:async()=>selector==='#tag-area .tag'?nodes.length:(node?1:0),
 evaluateAll:async(fn,arg)=>fn(nodes,arg),
 getAttribute:async k=>node.getAttribute(k),
 locator:child=>({click:async()=>assert.equal(node.guard,false,'site ignores edit click during new-tag guard'),
   fill:async value=>{node.pending=value;},press:async()=>{node.r.alias=node.pending;}})
};}
const page={url:()=> 'http://fixture/',evaluate:async()=>true,locator,
 waitForFunction:async(fn,arg)=>{
   if(typeof arg==='string'){assert.equal(fn(arg),false);find(arg).guard=false;guards++;}
   assert.equal(fn(arg),true);
 }};
(async()=>{const result=await run(page);assert.equal(result.status,'SELECTION_NAMES_PENDING');assert.equal(result.next_offset,4);assert.equal(guards,4);})()
.catch(e=>{console.error(e);process.exitCode=1;});
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'guard.cjs'
            path.write_text(fixture.replace('ACTION', browser_code(action, 'select'))
                            .replace('ROWS', json.dumps(action['selected'])), encoding='utf-8')
            result = subprocess.run(['node', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
