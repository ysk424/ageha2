"""Independent Blender BVH crossing and fixed-root checks on exported inputs."""
import sys,json,time,argparse
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import cache
from native import normalize
ap=argparse.ArgumentParser();ap.add_argument('runs',nargs='+');ap.add_argument('--frames',type=int,nargs='+',default=[1,22,23,100,164,200]);ap.add_argument('--output',type=Path,help='Write combined report here, leaving all input caches unchanged');a=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
inp=ROOT/'outputs/input';off=np.load(inp/'offsets.npy').astype(int);raw=np.load(inp/'raw_positions.npy');initial,repaired=normalize(raw,off)
targets=np.load(inp/'targets.npy',mmap_mode='r');verts=np.load(inp/'vertices.npy',mmap_mode='r');tri=np.load(inp/'triangles.npy')
fix=np.r_[off[:-1],off[:-1]+1]; edges=np.concatenate([np.arange(i,j-1) for i,j in zip(off[:-1],off[1:])]);rest=np.linalg.norm(initial[edges+1]-initial[edges],axis=1)
mapfix=[]
for sid in repaired:
 i,j=off[sid:sid+2];arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(raw[i:j].astype(float),axis=0),axis=1))];distance=arc[-1]/(j-i-1);edge=min(int(np.searchsorted(arc,distance,side='right')-1),j-i-2);w=(distance-arc[edge])/(arc[edge+1]-arc[edge]);mapfix.append((i+1,i+edge,i+edge+1,w))
reports={r:{} for r in a.runs}
for f in a.frames:
 bv=BVHTree.FromPolygons(verts[f-1].tolist(),tri.tolist(),all_triangles=True,epsilon=0)
 target=np.array(targets[f-1],copy=True)
 for i,j,k,w in mapfix:target[i]=targets[f-1,j]*(1-w)+targets[f-1,k]*w
 for run in a.runs:
  directory=Path(run) if Path(run).is_absolute() else ROOT/'outputs'/run
  if not (directory/f'frame_{f:06d}.k4c').exists():continue
  m=cache.load(directory);x=cache.read(directory,f,m['topology_hash'],m['parameter_hash'],m['points']);hits=[]
  output_offsets=np.load(directory/'offsets.npy').astype(int)
  edges=np.concatenate([np.arange(i,j-1) for i,j in zip(output_offsets[:-1],output_offsets[1:])])
  rest_x=np.load(directory/'initial_visible.npy') if (directory/'initial_visible.npy').exists() else initial
  rest=np.linalg.norm(rest_x[edges+1]-rest_x[edges],axis=1)
  output_fix=np.r_[output_offsets[:-1],output_offsets[:-1]+1]
  for i in edges:
   delta=x[i+1]-x[i];length=float(np.linalg.norm(delta))
   if length<1e-8:continue
   co,n,index,d=bv.ray_cast(Vector(x[i]),Vector(delta/length),length)
   if index is not None and 1e-6<float(d)<length-1e-6:hits.append(int(i))
  errors=np.abs(np.linalg.norm(x[edges+1]-x[edges],axis=1)/rest-1)
  r=dict(crossings=len(hits),crossing_strands=len(set(np.searchsorted(output_offsets,hits,side='right')-1)),edges=hits,root_error=float(np.max(np.abs(x[output_fix]-target[fix]))),finite=bool(np.isfinite(x).all()),visible_length_max=float(errors.max()),visible_length_p99=float(np.percentile(errors,99)))
  reports[run][str(f)]=r;print(run,f,json.dumps({k:v for k,v in r.items() if k!='edges'}),flush=True)
if a.output:
 a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text(json.dumps(reports,indent=2),encoding='utf8')
else:
 for run,r in reports.items():
  directory=Path(run) if Path(run).is_absolute() else ROOT/'outputs'/run
  (directory/'contact_check.json').write_text(json.dumps(r,indent=2),encoding='utf8')
