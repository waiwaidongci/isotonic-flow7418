import {useState} from 'react';import {PageHeading} from '../components/common/PageHeading';import {Table} from '../components/common/Table';import {Notice} from '../components/common/Notice';import {useTask} from '../hooks/useTask';import {collectApi} from '../api/collect';import {VOLUME_STATUS} from '../constants/enums';import {fmt,clock} from '../utils/format';import type {Volume} from '../types/domain';
const encoder=new TextEncoder();
const toB64=(bytes:Uint8Array)=>{let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s)};
const hash=(b:Uint8Array)=>{let h=7;for(const x of b)h=(h*31+x)>>>0;return h.toString(36)};
const ident=(key:string,gen:number)=>`指纹-${key}-${gen}`;
const sample='FW9-F10-P01,10,2.01\nFW9-F10-P02,10,2.13\nFW9-F20-P01,20,3.05\n坏行,not-a-number,?\nFW9-F20-P02,20,3.11\nFW9-F30-P01,30,4.02\nFW9-F30-P02,30,4.10\n';
export function CollectPage({studies,volumes,quarantine,ingest,user,reloadCollect,reloadSource}:any){
 const [studyId,S]=useState(0),[keyInput,K]=useState('fw-pressure-9-202611.csv'),[target,T]=useState(''),[raw,R]=useState(sample),[size,Z]=useState(24),[note,SN]=useState(''),task=useTask();
 const study=studies.find((s:any)=>s.id===(studyId||studies[0]?.id)),mine=volumes.filter((v:Volume)=>v.study_id===study?.id),open=mine.filter((v:Volume)=>v.status!=='sealed');
 const current=open.find((v:Volume)=>`${v.volume_key}#${v.generation}`===target)||open[open.length-1];
 async function send(retryLast:boolean){
  if(!current)throw Error('请先开卷或换卷');
  const fresh=await collectApi.volumes(),v=fresh.find((x:Volume)=>x.id===current.id);
  if(!v||v.status!=='active')throw Error('卷未处于采集中，请核对台账');
  const bytes=encoder.encode(raw);if(!bytes.length)throw Error('日志为空');
  let offset=v.offset,last:any=null,lastChunk:any=null,stored=0,quarantined=0;
  for(let p=0;p<bytes.length;p+=Math.max(4,size|0)){
   const c=bytes.subarray(p,Math.min(p+Math.max(4,size|0),bytes.length)),cid=`${v.volume_key}#${v.generation}#${offset}#${c.length}#${hash(c)}`;
   last=await collectApi.append({volume_key:v.volume_key,generation:v.generation,identity:ident(v.volume_key,v.generation),base_offset:offset,chunk_id:cid,data_b64:toB64(c)});
   offset=last.offset;stored+=last.stored;quarantined+=last.quarantined;lastChunk={c,cid};
  }
  let note=`已按块追加 ${bytes.length} 字节：入库 ${stored} 条、隔离 ${quarantined} 条，累计进度 ${offset} 字节`;
  if(retryLast&&lastChunk){
   const dup=await collectApi.append({volume_key:v.volume_key,generation:v.generation,identity:ident(v.volume_key,v.generation),base_offset:offset-lastChunk.c.length,chunk_id:lastChunk.cid,data_b64:toB64(lastChunk.c)});
   note+=dup.duplicate?'；末块重发被识别为重复块，未重复入库':'；末块重发未被识别，请核查';
  }
  await reloadCollect();await reloadSource();return note;
 }
 async function rotate(){
  if(!study)throw Error('请先选择研究');
  const same=volumes.filter((v:Volume)=>v.volume_key===keyInput),next=same.length?Math.max(...same.map((v:Volume)=>v.generation))+1:1;
  const v=await collectApi.open({study_id:study.id,volume_key:keyInput,generation:next,identity:ident(keyInput,next)});
  T(`${v.volume_key}#${v.generation}`);await reloadCollect();return `已开卷 ${v.volume_key} 第${v.generation}代；旧代仍可追加接尾`;
 }
 async function truncate(){
  if(!current)throw Error('请先开卷或换卷');
  const fresh=await collectApi.volumes(),v=fresh.find((x:Volume)=>x.id===current.id);
  if(!v||v.offset===0)throw Error('空卷无法模拟截断');
  const stale=Math.max(0,v.offset-13);
  try{await collectApi.append({volume_key:current.volume_key,generation:current.generation,identity:ident(current.volume_key,current.generation),base_offset:stale,chunk_id:`truncate#${Date.now()}`,data_b64:toB64(encoder.encode('FW9-XX-P01,10,1.0\n'))})}finally{await reloadCollect()}
 }
 const act=async(fn:()=>Promise<any>,ok:string)=>{SN('');const r=await task.act(fn,ok);if(typeof r==='string'&&r)SN(r)};
 return <><PageHeading index="03" title="断点续采，半条留待补齐。" description="按卷身份与字节进度接续；坏记录隔离留原文，异常卷暂停不拖住其他卷。"/>
 <div className="source-layout"><section>
  <div className="section-head"><h2>采集卷台账</h2><span>{volumes.length} 卷 / 进度落库，重启接续</span></div>
  <Table headers={['卷 / 代次','研究','状态','字节进度 / 行数','待补齐','入库 / 隔离','操作']}>{volumes.map((v:Volume)=><tr key={v.id} className={current?.id===v.id?'target-row':''}><td>{v.volume_key} <small>第{v.generation}代</small></td><td>{studies.find((s:any)=>s.id===v.study_id)?.name||v.study_id}</td><td><span className={'status '+v.status}>{VOLUME_STATUS[v.status]||v.status}</span>{v.error&&<small className="error-line">{v.error}</small>}</td><td>{v.offset} B / {v.lines} 行</td><td className="pending-raw">{v.pending_bytes?`${v.pending_preview}（${v.pending_bytes}B）`:'—'}</td><td>{v.stored} / {v.quarantined}</td><td>{user.role!=='viewer'&&<>{v.status==='active'&&<button onClick={()=>act(async()=>{await collectApi.pause(v.id);await reloadCollect()},'卷已人工暂停')}>暂停</button>}{v.status==='paused'&&<button onClick={()=>act(async()=>{await collectApi.resume(v.id);await reloadCollect()},'卷已恢复，按已存字节进度接续')}>恢复</button>}{v.status!=='sealed'&&<button onClick={()=>act(async()=>{await collectApi.seal(v.id);await reloadCollect()},'卷已封存；卷尾半条记录已隔离')}>封存</button>}<button onClick={()=>{T(`${v.volume_key}#${v.generation}`);K(v.volume_key)}}>选为追加目标</button></>}</td></tr>)}</Table>
  <h2 className="spaced">入库读数 / 溯源前12条</h2>
  <Table headers={['滤片编号','压差 kPa','流速档','卷 / 行号','时间']}>{ingest.slice(0,12).map((i:any)=><tr key={i.id}><td>{i.specimen_ref}</td><td>{fmt(i.pressure,6)}</td><td>{fmt(i.flow)}</td><td>{i.volume_key} 第{i.generation}代 / 行{i.line_no}</td><td>{clock(i.created_at)}</td></tr>)}</Table>
 </section>
 <section className="input-panel"><small>RESUMABLE COLLECTION</small><h2>模拟试验仪追加</h2>
  <label>目标研究<select value={study?.id||''} onChange={e=>S(+e.target.value)}>{studies.map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
  <div className="field-pair"><label>卷名<input value={keyInput} onChange={e=>K(e.target.value)}/></label><label>追加目标<select value={current?`${current.volume_key}#${current.generation}`:''} onChange={e=>T(e.target.value)}>{open.map((v:Volume)=><option key={v.id} value={`${v.volume_key}#${v.generation}`}>{v.volume_key} 第{v.generation}代（{VOLUME_STATUS[v.status]}）</option>)}</select></label></div>
  {user.role!=='viewer'?<>
  <button className="text-action" onClick={()=>act(rotate,'')}>开卷 / 换卷（新代次）↗</button>
  <label>日志文本（每行：滤片编号,流速,压差[,说明]）<textarea rows={8} value={raw} onChange={e=>R(e.target.value)}/></label>
  <label>读取块大小（字节，小块可制造跨块半条记录）<input type="number" min="4" max="4096" value={size} onChange={e=>Z(+e.target.value)}/></label>
  <button className="primary" disabled={task.busy||!current} onClick={()=>act(()=>send(false),'')}>逐块追加 →</button>
  <div className="note-actions">
   <button disabled={task.busy||!current} onClick={()=>act(()=>send(true),'')}>追加并重发末块（崩溃重发）</button>
   <button disabled={task.busy||!current} onClick={()=>act(truncate,'')}>模拟截断（旧进度重读）</button>
  </div>
  <p>换卷后旧代仍在台账中，选为追加目标即可接完旧卷尾记录；截断或同名换卷会暂停该卷，不影响其他卷。</p>
  </>:<p>观察员可核对台账、待补齐与隔离记录；采集操作由试验员执行。</p>}
  <Notice error={task.error} message={note||task.message}/>
 </section></div>
 <section className="ledger-section"><div className="section-head"><h2>待补齐与隔离核对</h2><span>半条记录留在卷内等后续字节；坏记录保留原文不入库</span></div>
 <div className="collect-grid"><div><h2>待补齐半条记录</h2><Table headers={['卷 / 代次','已存进度','待补齐原文']} >{volumes.filter((v:Volume)=>v.pending_bytes>0).map((v:Volume)=><tr key={v.id}><td>{v.volume_key} 第{v.generation}代</td><td>{v.offset} B</td><td className="pending-raw">{v.pending_preview}</td></tr>)}</Table></div>
 <div><h2>隔离记录 / 前12条</h2><Table headers={['卷 / 行号','原因','原文']} >{quarantine.slice(0,12).map((q:any)=><tr key={q.id}><td>{q.volume_key} 第{q.generation}代 / {q.line_no?`行${q.line_no}`:'卷尾'}</td><td>{q.reason}</td><td className="pending-raw">{q.raw}</td></tr>)}</Table></div></div></section></>}
