"""Measure rendered Criteria disclosure with a local, offline browser.

Used only by explicitly scoped unknown-published-source policies. Ordinary topics
retain their existing checks. Missing browser support blocks this extra mode.
"""
import os

def visible_criteria_texts(markup,variables,disclosure):
 try:
  from playwright.sync_api import sync_playwright
 except ImportError as error:
  raise ValueError('Scoped disclosure visibility requires the Python Playwright runtime') from error
 try:
  with sync_playwright() as runtime:
   browser=runtime.chromium.launch(channel='msedge' if os.name=='nt' else 'chromium',headless=True)
   try:
    context=browser.new_context(java_script_enabled=False,offline=True,viewport={'width':1440,'height':1000})
    page=context.new_page();page.route('**/*',lambda route:route.abort())
    page.set_content(markup,wait_until='domcontentloaded')
    if page.locator('link[rel="stylesheet"]').count():raise ValueError('External stylesheets prevent offline disclosure visibility proof')
    return page.evaluate('''({variables,disclosure}) => {
      const normalize=s=>s.replace(/\\s/g,'').replace(/`/g,'');
      const wanted=normalize(disclosure);
      function rgb(value) {
        const match=value.match(/^rgba?\\(([^)]+)\\)$/);
        if(!match)return null;
        const v=match[1].split(',').map(Number);
        return v.length===3?[...v,1]:v;
      }
      function light(v){return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4;}
      function luminance(c){return .2126*light(c[0]/255)+.7152*light(c[1]/255)+.0722*light(c[2]/255);}
      function visibleText(cell) {
        const walker=document.createTreeWalker(cell,NodeFilter.SHOW_TEXT);let text='',node;
        while(node=walker.nextNode()) {
          if(!normalize(node.textContent).includes(wanted)) continue;
          // The locked disclosure is a plain renderer paragraph, not text assembled
          // through arbitrary styled descendants or an overlaid child element.
          if(node.parentElement.childElementCount!==0)continue;
          node.parentElement.scrollIntoView({block:'center',inline:'center'});
          const range=document.createRange();range.selectNodeContents(node);
          let rectangles=Array.from(range.getClientRects()).filter(r=>r.width>0&&r.height>0);
          let accepted=rectangles.length>0;
          const targetBox=node.parentElement.getBoundingClientRect();
          for(const other of document.querySelectorAll('*')) {
            const style=getComputedStyle(other);
            if(style.display==='none'||['hidden','collapse'].includes(style.visibility)||Number(style.opacity)===0)continue;
            let suppressed=false;
            for(let owner=other;owner;owner=owner.parentElement) {
              if(getComputedStyle(owner).display==='none')suppressed=true;
              if(owner.tagName==='DETAILS'&&!owner.open&&owner!==other) {
                const summary=Array.from(owner.children).find(c=>c.tagName==='SUMMARY');
                if(!summary||!(summary===other||summary.contains(other)))suppressed=true;
              }
            }
            if(suppressed)continue;
            for(const pseudo of ['::before','::after']) {
              const p=getComputedStyle(other,pseudo);
              const ownerBox=other.getBoundingClientRect();
              const separated=ownerBox.bottom+32<=targetBox.top||ownerBox.top-32>=targetBox.bottom||ownerBox.right+32<=targetBox.left||ownerBox.left-32>=targetBox.right;
              let arrow=false;
              if(other.matches('.variable-map details summary')&&['"▶"','"▼"'].includes(p.content)&&p.fontSize==='15px'&&p.position==='absolute'&&p.left==='14px'&&separated&&ownerBox.width>=32&&ownerBox.height>=15&&p.backgroundColor==='rgba(0, 0, 0, 0)'&&p.boxShadow==='none'&&p.textShadow==='none'&&p.filter==='none'&&p.clipPath==='none') {
                const m=new DOMMatrixReadOnly(p.transform==='none'?undefined:p.transform);
                arrow=m.a===1&&m.d===1&&m.b===0&&m.c===0&&Math.abs(m.e)<=1&&Math.abs(m.f)<=16;
              }
              if(!arrow&&!['none','normal',''].includes(p.content)&&p.display!=='none'&&p.visibility!=='hidden'&&Number(p.opacity)>0&&
                (p.position!=='static'||p.transform!=='none'||p.filter!=='none'||p.cssFloat!=='none'||p.boxShadow!=='none'||
                ['marginLeft','marginRight','marginTop','marginBottom'].some(k=>parseFloat(p[k])<0)))accepted=false;
            }
            if(other===node.parentElement||other.contains(node.parentElement)||node.parentElement.contains(other))continue;
            if(style.filter!=='none')accepted=false;
            const box=other.getBoundingClientRect();
            if(box.width<=0||box.height<=0)continue;
            // Paint can obscure text even with pointer-events:none. Conservatively
            // reject overlapping unrelated layout boxes, not just hit-test owners.
            const outline=['none','hidden'].includes(style.outlineStyle)?'':style.outlineWidth;
            const effects=[style.boxShadow,style.textShadow,style.filter,outline].join(' ');
            const pixels=effects.match(/-?[0-9.]+px/g)||[];
            const pad=pixels.length?Math.max(...pixels.map(v=>Math.abs(parseFloat(v))))*2:0;
            if(box.right+pad>targetBox.left&&box.left-pad<targetBox.right&&box.bottom+pad>targetBox.top&&box.top-pad<targetBox.bottom)accepted=false;
          }
          let background=[255,255,255,1],backgroundFound=false;
          for(let parent=node.parentElement;parent&&accepted;parent=parent.parentElement) {
            const style=getComputedStyle(parent);
            if(parent.hidden||parent.getAttribute('aria-hidden')==='true'||
              ['SCRIPT','STYLE','TEMPLATE','NOSCRIPT'].includes(parent.tagName)||
              style.display==='none'||['hidden','collapse'].includes(style.visibility)||
              Number(style.opacity)!==1||parseFloat(style.fontSize)<12||
              ['absolute','fixed','sticky'].includes(style.position)||
              style.transform!=='none'||style.filter!=='none'||style.clipPath!=='none'||
              (style.maskImage&&style.maskImage!=='none')||style.backgroundImage!=='none'||
              style.textShadow!=='none'||style.boxShadow.includes('inset')||style.animationName!=='none') accepted=false;
            if(style.position==='relative'&&['top','left','right','bottom'].some(k=>!['auto','0px'].includes(style[k])))accepted=false;
            const bg=rgb(style.backgroundColor);
            if(!backgroundFound&&bg&&bg[3]>0){background=bg;backgroundFound=true;}
            if(accepted&&['hidden','clip'].some(v=>style.overflowX===v||style.overflowY===v)) {
              const box=parent.getBoundingClientRect();
              accepted=rectangles.some(r=>r.right>box.left&&r.left<box.right&&r.bottom>box.top&&r.top<box.bottom);
            }
          }
          const foreground=rgb(getComputedStyle(node.parentElement).color);
          if(!foreground||foreground[3]!==1||background[3]!==1)accepted=false;
          if(accepted) {
            const a=luminance(foreground),b=luminance(background);
            if((Math.max(a,b)+.05)/(Math.min(a,b)+.05)<4.5)accepted=false;
          }
          // Every painted non-space character must lie in the accessible viewport
          // after scrolling and hit the disclosure's own element, not an overlay.
          for(let i=0;i<node.length&&accepted;i++) {
            if(!node.textContent[i].trim())continue;
            range.setStart(node,i);range.setEnd(node,i+1);
            const box=range.getBoundingClientRect();
            if(box.width<=0||box.height<=0||box.left<0||box.top<0||box.right>innerWidth||box.bottom>innerHeight){accepted=false;break;}
            const hit=document.elementFromPoint((box.left+box.right)/2,(box.top+box.bottom)/2);
            if(!hit||!(hit===node.parentElement||hit.contains(node.parentElement)))accepted=false;
          }
          if(accepted) text+=node.textContent;
        }
        return text;
      }
      const rows=Array.from(document.querySelectorAll('tr')).map(row=>Array.from(row.children).filter(c=>c.tagName==='TD'));
      return Object.fromEntries(variables.map(variable=>{
        const matches=rows.filter(cells=>cells.length===3&&cells[0].textContent.trim()===variable);
        return [variable,matches.length===1?visibleText(matches[0][1]):null];
      }));
    }''',{'variables':variables,'disclosure':disclosure})
   finally:browser.close()
 except ValueError:raise
 except Exception as error:
  raise ValueError('Scoped rendered disclosure visibility could not be established: '+str(error)) from error
