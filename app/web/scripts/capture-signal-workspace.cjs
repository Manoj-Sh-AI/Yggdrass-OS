// Read-only verification of the running application. Never logs credentials or note contents.
const {chromium} = require('@playwright/test');
const {readFileSync} = require('node:fs');
const path = require('node:path');
(async()=>{
  const runtime=path.resolve(__dirname,'../../api/runtime');
  const signIn=JSON.parse(readFileSync(path.join(runtime,'preview-session.json'),'utf8'));
  const browser=await chromium.launch({channel:'msedge',headless:true,args:['--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
  try{
    const page=await browser.newPage();
    const login=await page.request.post(signIn.origin+'/api/backend/auth/login',{data:{password:signIn.password},headers:{Origin:signIn.origin}});
    if(!login.ok())throw new Error('Sign-in verification failed.');
    for(const [size,viewport] of [['desktop',{width:1344,height:896}],['tablet',{width:820,height:1180}],['mobile',{width:390,height:844}]]){
      await page.setViewportSize(viewport);
      for(const name of ['today','calendar','tasks','notes','graph']){
        await page.goto(signIn.origin+'/'+name,{waitUntil:'domcontentloaded'});
        await page.locator('.signal-workspace').waitFor({timeout:60000});
        if(name==='today')await page.locator('.today-schedule').waitFor({timeout:60000});
        if(name==='calendar'){
          await page.getByRole('tab',{name:'Month',exact:true}).click();
          await page.locator('.calendar-grid').waitFor({timeout:60000});
        }
        if(name==='tasks')await page.locator('.planning-tasks-panel').waitFor({timeout:60000});
        if(name==='notes'){
          await page.locator('.bn-editor').waitFor({timeout:90000});
          if(await page.locator('.editor-error[role="alert"]').count())throw new Error('Notes reports an error.');
        }
        if(name==='graph'){
          await page.locator('.brain-graph-stage[aria-busy="false"]').waitFor({timeout:90000});
          if(await page.locator('.brain-graph-error').count())throw new Error('Graph reports an error.');
          if(await page.getByRole('button',{name:'Resume rotation',exact:true}).getAttribute('aria-pressed')!=='true')throw new Error('Graph rotation is not paused.');
          await page.frameLocator('iframe').locator('body[data-spin="0"]').waitFor({timeout:30000});
        }
        if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error(name+' has page overflow at '+size);
        await page.screenshot({path:path.join(runtime,'signal-'+name+'-'+size+'.png'),animations:'disabled'});
        console.log(name+' '+size+' verified and captured.');
      }
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1});
