"""Portable synthetic regression cases for CHARLS mixed-source evidence."""
import copy, hashlib, json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mixed_source_evidence import validate_mixed
from source_read import receipt_hash

class MixedEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.binding={'schema':'dbcodebook.local-binding.v1','ok':True,'database':'charls','language':None,
            'website_url':'http://fixture/home/charls/','dictionary_sha256':'a'*64,
            'periods':['2011','2013'],'mapping':{'kind':'runtime_settings_same_file'}}
        self.bref=self.save('binding.json',self.binding)
        self.local={'schema':'dbcodebook.local-source.v1','ok':True,'database':'charls','language':None,
            'binding_sha256':self.bref['sha256'],'dictionary_sha256':'a'*64,
            'request':{'kind':'detail','variable':'A','file':'F','periods':['2013']},
            'sources':[{'variable':'A','file':'F','periods':[{'period':'2013','available':True,'actual_variable':'A','source_identity':'A (F)'}]}]}
        self.lref=self.save('local.json',self.local)
        action={'kind':'detail','variable':'A','file':'F','periods':['2011']}
        detail={'identity':'A (F)','period':'2011','status':'DETAIL_READ'}
        receipt={'action':action,'ok':True,'status':'SOURCE_READ','operation_completed':True,'details':[detail]}
        self.web={'ok':True,'status':'SOURCE_READ','binding':{'action':action,'database':'charls',
            'url':'http://fixture/home/charls/','helper_sha256':'b'*64},
            'completed':[{'index':0,'sha256':receipt_hash(receipt),'result':{k:v for k,v in receipt.items() if k!='details'},'details_slice':[0,1]}],
            'details':[detail],'pending':None,'failed':None}
        self.wref=self.save('web.json',self.web)
        self.record={'database':'CHARLS','dbcodebook_url':'http://fixture/home/charls/',
            'source_access':{'mode':'mixed_charls_v1','local':{'mode':'local_dictionary','binding':self.bref,'receipts':[self.lref]},
                'web_receipts':[self.wref],'required_identity_periods':[{'identity':'A (F)','period':'2011','channel':'web'},{'identity':'A (F)','period':'2013','channel':'local'}]},
            'source_groups':[{'source_identities':['A (F)'],'periods':['2011','2013']}]}
    def save(self,name,data):
        p=self.root/name;p.write_text(json.dumps(data),encoding='utf-8')
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    def validate(self,record=None):return validate_mixed(record or self.record,self.root/'record.json')
    def test_real_shape_and_period_coverage(self):
        self.assertEqual(self.validate()['sources'],{('A (F)','2011'),('A (F)','2013')})
        for edit in ('omit','wrong_period','wrong_identity','wrong_channel','duplicate','multi_identity'):
            with self.subTest(edit=edit):
                r=copy.deepcopy(self.record);plan=r['source_access']['required_identity_periods']
                if edit=='omit':plan.pop()
                elif edit=='wrong_period':plan[0]['period']='2099'
                elif edit=='wrong_identity':plan[0]['identity']='wrong (F)'
                elif edit=='wrong_channel':plan[0]['channel']='local'
                elif edit=='duplicate':plan.append(copy.deepcopy(plan[0]))
                else:r['source_groups'][0]['source_identities'].append('other (F)')
                with self.assertRaises(ValueError):self.validate(r)
    def test_website_and_binding_are_not_interchangeable(self):
        for edit in ('url','database','web_hash','local_hash','local_binding'):
            with self.subTest(edit=edit):
                r=copy.deepcopy(self.record)
                if edit=='url':r['dbcodebook_url']='http://wrong/home/charls/'
                elif edit=='database':r['database']='HRS'
                elif edit=='web_hash':r['source_access']['web_receipts'][0]['sha256']='0'*64
                elif edit=='local_hash':r['source_access']['local']['receipts'][0]['sha256']='0'*64
                else:
                    local=copy.deepcopy(self.local);local['binding_sha256']='c'*64
                    r['source_access']['local']['receipts']=[self.save('bad_local.json',local)]
                with self.assertRaises(ValueError):self.validate(r)
    def test_incomplete_or_tampered_web_not_evidence(self):
        for edit in ('tamper_inner','pending','not_completed'):
            with self.subTest(edit=edit):
                r=copy.deepcopy(self.record);web=copy.deepcopy(self.web)
                if edit=='tamper_inner':web['details'][0]['period']='2099'
                elif edit=='pending':web['completed']=[];web['pending']={'index':0}
                else:
                    web['completed'][0]['result']['operation_completed']=False
                    rec={**web['completed'][0]['result'],'details':web['details']}
                    web['completed'][0]['sha256']=receipt_hash(rec)
                r['source_access']['web_receipts']=[self.save('bad_web.json',web)]
                with self.assertRaises(ValueError):self.validate(r)
    def test_overlap_is_rejected(self):
        local=copy.deepcopy(self.local)
        local['request']['periods'].append('2011')
        local['sources'][0]['periods'].append({'period':'2011','available':True,'actual_variable':'A','source_identity':'A (F)'})
        r=copy.deepcopy(self.record);r['source_access']['local']['receipts']=[self.save('overlap.json',local)]
        with self.assertRaisesRegex(ValueError,'Overlapping'):self.validate(r)

if __name__=='__main__':unittest.main()
