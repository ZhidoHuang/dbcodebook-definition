"""Cancellation must target the bound page, never accept or silently succeed."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from playwright_session_action import bind_code, Session


def main():
    code = bind_code('async page => {await page.trigger(); return {ok:true};}', 'A')
    fixture = r'''
const assert = require('node:assert/strict');
let calls=[], message='是否清空所有标签？', type='confirm', fail=false;
const pages=['B','A'].map(id=>({id,isClosed:()=>false,url:()=>id,context:()=>context,
  handlers:new Set(),on:(event,handler)=>{assert.equal(id,'A');pages[1].handlers.add(handler);},
  off:(event,handler)=>pages[1].handlers.delete(handler),
  trigger:async()=>{for(const fn of pages[1].handlers) fn({type:()=>type,message:()=>message,
    dismiss:async()=>{calls.push(id);if(fail)throw new Error('dismiss failed');}});}
}));
const context={pages:()=>pages,newCDPSession:async page=>({
  send:async (name,args)=>{
    if(name==='Target.getTargetInfo') return {targetInfo:{targetId:page.id}};
    throw new Error('unexpected command');
  },detach:async()=>{}
})};
'''
    fixture += '\nconst run=' + code + ';\n'
    fixture += '''(async()=>{
assert.equal((await run(pages[0])).native_dialogs[0].confirmed,true);
assert.equal(pages[1].handlers.size,0); assert.equal(pages[0].handlers.size,0);
message='确定发布文章？'; assert.equal((await run(pages[0])).native_dialogs,undefined);
message='是否清空所有标签？';type='prompt'; assert.equal((await run(pages[0])).native_dialogs,undefined);
type='confirm';fail=true;await assert.rejects(run(pages[0]),/cancellation failed/);
assert.equal(pages[1].handlers.size,0);
pages.pop(); await assert.rejects(run(pages[0]),/Bound tab/);
assert.deepEqual(calls,['A','A']);
console.log('BOUND_DIALOG_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});'''
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'dialog.cjs'
        path.write_text(fixture,encoding='utf-8')
        subprocess.run(['node',str(path)],check=True)
        session=Session.__new__(Session)
        session.tab_id='A'
        session.code_path=Path(folder)/'action.js'
        emitted=[]
        def call(*args):
            emitted.append(session.code_path.read_text(encoding='utf-8'))
            return '' if len(emitted)==1 else '{"ok":true}'
        with patch.object(session,'call',side_effect=call):
            assert session.code('async page=>{await page.locator("#once").click();return {ok:true};}')=={'ok':True}
        assert '#once' in emitted[0] and '#once' not in emitted[1]
        assert 'receipt.id !==' in emitted[1] and 'receipt.operation' in emitted[1]


if __name__=='__main__': main()
