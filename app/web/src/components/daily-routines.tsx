"use client";
import { useEffect, useState } from "react";
import { applicationApi } from "@/lib/api";
import { Panel } from "./ui";
import { enableRoutinePush } from "@/lib/routine-push";

type Brief = {kind:string;text:string};
type Lesson = {id:string;text:string;status:string};
type Snapshot = {timezone:string;day:string;briefs:Brief[];lessons:Lesson[]};
const root="application/daily-routines";
export function DailyRoutines() {
  const [data,setData]=useState<Snapshot|null>(null);
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  const [worked,setWorked]=useState("");
  const [friction,setFriction]=useState("");
  const [tomorrow,setTomorrow]=useState("");
  const [outcome,setOutcome]=useState("partial");
  const [lesson,setLesson]=useState("");
  const [preview,setPreview]=useState("");
  async function load() { setData(await applicationApi<Snapshot>(root)); }
  useEffect(()=>{void load().catch(e=>setMessage(e.message));},[]);
  async function act(work:()=>Promise<unknown>) {
    setBusy(true);setMessage("");
    try {await work();await load();setMessage("Saved.");}
    catch(e) {setMessage(e instanceof Error?e.message:"Please try again.");}
    finally {setBusy(false);}
  }
  return <div className="standard-page">
    <div className="page-intro"><h1>Daily routines</h1></div>
    <p role="status">{message}</p>
    <Panel title="Briefs">
      <button className="button" disabled={busy} onClick={()=>void act(enableRoutinePush)}>Enable notifications on this device</button>
      <button className="button" disabled={busy} onClick={()=>void act(async()=>{
        const result=await applicationApi<Brief>(root+"/trigger",{method:"POST",body:JSON.stringify({kind:"morning",dry_run:true})});
        setPreview(result.text);
      })}>Preview morning brief</button>
      {preview&&<p style={{whiteSpace:"pre-wrap"}}>{preview}</p>}
      {data?.briefs.map((b,i)=><article key={i}><h2>{b.kind==="morning"?"Morning brief":"Evening review"}</h2><p style={{whiteSpace:"pre-wrap"}}>{b.text}</p></article>)}
    </Panel>
    <Panel title="Evening review">
      <form onSubmit={e=>{e.preventDefault();void act(async()=>{
        await applicationApi(root+"/review",{method:"POST",body:JSON.stringify({
          key:crypto.randomUUID(),outcome,worked,friction,tomorrow,lessons:lesson.trim()?[lesson.trim()]:[]
        })});
        setWorked("");setFriction("");setTomorrow("");setLesson("");
      });}}>
        <label>Today's focus<select value={outcome} onChange={e=>setOutcome(e.target.value)}>
          <option value="yes">Done</option><option value="partial">Partly done</option><option value="no">Still open</option><option value="skip">Skip</option>
        </select></label>
        <label>What worked?<textarea maxLength={500} value={worked} onChange={e=>setWorked(e.target.value)}/></label>
        <label>One friction<textarea maxLength={500} value={friction} onChange={e=>setFriction(e.target.value)}/></label>
        <label>Tomorrow's first step<input maxLength={400} value={tomorrow} onChange={e=>setTomorrow(e.target.value)}/></label>
        <label>Possible lesson<input maxLength={400} value={lesson} onChange={e=>setLesson(e.target.value)}/></label>
        <button className="button primary" disabled={busy}>Save review</button>
      </form>
    </Panel>
    {!!data?.lessons.length&&<Panel title="Lessons">
      {data.lessons.map(l=><article key={l.id}><p>{l.text}</p><small>{l.status}</small>
        {l.status==="candidate"&&<button className="button" disabled={busy} onClick={()=>void act(()=>applicationApi(root+"/lessons",{method:"POST",body:JSON.stringify({id:l.id,decision:"confirm"})}))}>Keep this lesson</button>}
      </article>)}
    </Panel>}
  </div>;
}
