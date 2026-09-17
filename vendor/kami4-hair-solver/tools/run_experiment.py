import sys,json,time,argparse,hashlib,traceback
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
from native import Solver,parameters,parameter_hash,BINARY_PATH
import cache

def run():
 ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--frames',type=int,default=200);ap.add_argument('--resident',action='store_true');ap.add_argument('--contact-mode',type=int,default=0);ap.add_argument('--min-length',type=float,default=0);ap.add_argument('--max-element',type=float,default=.01);ap.add_argument('--visible-element',type=float,default=0);ap.add_argument('--baseline');ap.add_argument('--substeps',type=int);ap.add_argument('--passes',type=int);ap.add_argument('--extension-iterations',type=int,default=4);ap.add_argument('--parameters',type=Path,help='Exact parameter JSON; do not combine with physical parameter overrides');a=ap.parse_args()
 if a.parameters:
  overrides={'--contact-mode','--min-length','--max-element','--visible-element','--substeps','--passes','--extension-iterations'}
  if any(token.split('=')[0] in overrides for token in sys.argv[1:]):ap.error('--parameters cannot be combined with physical parameter overrides')
 inp=ROOT/'outputs/input';out=ROOT/'outputs'/a.name;out.mkdir(parents=True,exist_ok=False)
 x=np.load(inp/'raw_positions.npy');off=np.load(inp/'offsets.npy');targets=np.load(inp/'targets.npy',mmap_mode='r');verts=np.load(inp/'vertices.npy',mmap_mode='r');tri=np.load(inp/'triangles.npy')
 if a.parameters:
  p=parameters(a.parameters)
  if p.get('root_points')!=2:raise ValueError('This comparison runner requires root_points=2')
 else:
  p=parameters();p.update(mesh_contact_mode=a.contact_mode,minimum_dynamic_length=a.min_length,maximum_extension_element_length=a.max_element,extension_length_iterations=a.extension_iterations,maximum_visible_element_length=float(a.visible_element),root_points=2)
  if a.substeps:p['substeps']=a.substeps
  if a.passes:p['length_passes']=a.passes
 (out/'parameters.json').write_text(json.dumps(p,indent=2),encoding='utf8')
 fixed=np.zeros(len(x),np.uint8);fixed[off[:-1]]=1;fixed[off[:-1]+1]=1
 init=time.perf_counter();s=Solver(x,off,fixed,p,dt=1/24,max_colliders=0);s.set_mesh(verts[0],tri)
 if a.resident:s.set_animation(targets[:a.frames],verts[:a.frames])
 s.prepare(0);prepare_seconds=time.perf_counter()-init
 np.save(out/'initial_visible.npy',s.x);m=cache.create(out,s.x,s.offsets,p,parameter_hash(p),binary_hash=hashlib.sha256(BINARY_PATH.read_bytes()).hexdigest(),root_points=2,resident=a.resident)
 bm=cache.load(a.baseline) if a.baseline else None
 rows=[];difference=0.;started=time.perf_counter();failure=None
 try:
  for f in range(a.frames):
   t=time.perf_counter()
   st=s.step_animation(f) if a.resident else s.step(targets[f],mesh_previous=verts[max(0,f-1)],mesh_next=verts[f])
   st.update(frame=f+1,total_ms=(time.perf_counter()-t)*1000)
   if p.get('mesh_contact_mode')==2:
    fk=s.fk_data();st.update(fk_queries=int(fk[:,0].sum()),fk_repairs=int(fk[:,1].sum()),fk_max_rewind=int(fk[:,2].max()),fk_unresolved=int(fk[:,3].sum()),fk_moved_points=int(fk[:,4].sum()),fk_strands=int(fk[:,5].sum()),fk_repairs_max=int(fk[:,1].max()))
   if bm:
    expected=cache.read(a.baseline,f+1,bm['topology_hash'],bm['parameter_hash'],bm['points']);difference=max(difference,float(np.max(np.abs(s.x-expected))))
   cache.write(out,f+1,s.x,m);rows.append(st)
   with (out/'stats.jsonl').open('a') as file:file.write(json.dumps(st)+'\n')
   if (f+1)%25==0:print(a.name,f+1,round(st['native_ms'],3),flush=True)
 except Exception as e:
  failure={'message':str(e),'traceback':traceback.format_exc()};print(failure,flush=True)
 elapsed=time.perf_counter()-started;cache.save_manifest(out,m)
 report={'frames':len(rows),'requested_frames':a.frames,'failure':failure,'prepare_seconds':prepare_seconds,'seconds':elapsed,'parameters':p,'baseline_max_difference':difference if bm else None,'root_points':2,'resident':a.resident,'points':len(s.x),'internal_points':len(getattr(s,'internal_x',s.x))}
 if rows:
  for field in ['native_ms','upload_ms','download_ms','total_ms']:report[field+'_median']=float(np.median([r[field] for r in rows]))
  for field in ['max_length_error','p99_length_error','max_displacement','nonfinite','overflow']:report[field]=max(r[field] for r in rows)
  report['min_gap']=min(r['min_gap'] for r in rows)
 np.savez(out/'final_state.npz',x=s.x,v=s.v)
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');s.close();print(json.dumps(report,indent=2),flush=True)
 if failure:raise SystemExit(1)
if __name__=='__main__':run()
