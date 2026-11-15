// User-requested screenshots. Read-only navigation; credentials stay in memory.
const { chromium } = require('@playwright/test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
(async () => {
  const signIn = JSON.parse(readFileSync(path.resolve(__dirname,'../../api/runtime/preview-session.json'),'utf8'));
  const browser = await chromium.launch({channel:'msedge',headless:true,args:['--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
  try {
    const mobile=process.argv.includes('--mobile'), tablet=process.argv.includes('--tablet');
    const page = await browser.newPage({viewport:mobile?{width:390,height:844}:tablet?{width:820,height:1180}:{width:1344,height:896}});
    const signedIn = await page.request.post(signIn.origin+'/api/backend/auth/login', {data:{password:signIn.password},headers:{Origin:signIn.origin}});
    if(!signedIn.ok()) throw new Error('Local app sign-in returned HTTP '+signedIn.status());
    const requested=process.argv.slice(2).find(arg=>!arg.startsWith('--'));
    const openAir=process.argv.includes('--open-air');
    const refined=process.argv.includes('--refined');
    const targets=[['calendar','.unified-calendar-panel'],['notes','.bn-editor'],['graph','.brain-graph-stage[aria-busy="false"]']].filter(([name])=>!requested||name===requested);
    for(const [name,selector] of targets){
      await page.goto(signIn.origin+'/'+name,{waitUntil:'domcontentloaded'});
      if(name==='notes'){
        await page.locator('.notes-page-heading').waitFor({timeout:90000});
        if(mobile){
          await page.waitForTimeout(150);
          const toggle=page.getByRole('button',{name:'Toggle notes navigation'});
          if(await toggle.getAttribute('aria-expanded')==='false') await toggle.click();
        }
        await page.locator('.note-tree-item').first().waitFor({timeout:90000});
        if(!await page.locator('.bn-editor').count()) await page.locator('.note-tree-item').first().click();
      }
      try { await page.locator(selector).first().waitFor({timeout:90000}); }
      catch(error){await page.screenshot({path:path.resolve(__dirname,'../../api/runtime/current-'+name+'-unavailable.png')});console.log(name+' is not ready; captured its current state.');continue;}
      if(name==='calendar'){
        await page.getByRole('tab',{name:'Month',exact:true}).click();
        await page.locator('.calendar-grid').waitFor({timeout:90000});
      }
      if(name==='notes' && mobile){const toggle=page.getByRole('button',{name:'Toggle notes navigation'});if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();}
      if(name==='graph'){
        const pause=page.getByRole('button',{name:'Pause rotation',exact:true});
        if(await pause.isEnabled()) await pause.click();
      }
      if(openAir) await page.addStyleTag({path:path.resolve(__dirname,'../src/app/open-air.css')});
      await page.waitForTimeout(500);
      if(refined && !(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--glass-rgb').replace(/\s/g,'')==='32,34,35'))) throw new Error('The reviewed material is not active.');
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw new Error(name+' has horizontal page overflow.');
      await page.screenshot({path:path.resolve(__dirname,'../../api/runtime/'+(openAir||refined?'open-air-':'current-')+name+(mobile?'-mobile.png':tablet?'-tablet.png':'-desktop.png')),animations:'disabled'});
      console.log(name+' screenshot captured'+(name==='graph'&&await page.locator('.brain-graph-error').count()?' (viewer reports an error)':'')+'.');
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1});
