import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'))
import cache
from native import normalize
d=ROOT/'outputs/review_bvh_extension_200';m=cache.load(d);off=np.load(d/'offsets.npy').astype(int);raw=np.load(ROOT/'outputs/input/raw_positions.npy');initial,repaired=normalize(raw,off);target=np.load(ROOT/'outputs/input/targets.npy',mmap_mode='r')
fix=np.r_[off[:-1],off[:-1]+1];edges=np.concatenate([np.arange(a,b-1) for a,b in zip(off[:-1],off[1:])]);rest=np.linalg.norm(initial[edges+1]-initial[edges],axis=1)
mapping=[]
for sid in repaired:
 a,b=off[sid:sid+2];arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(raw[a:b].astype(float),axis=0),axis=1))];distance=arc[-1]/(b-a-1);edge=min(int(np.searchsorted(arc,distance,side='right')-1),b-a-2);w=(distance-arc[edge])/(arc[edge+1]-arc[edge]);mapping.append((a+1,a+edge,a+edge+1,w))
root_error=0.;length_max=0.;finite=True
for f in range(1,201):
 x=cache.read(d,f,m['topology_hash'],m['parameter_hash'],m['points']);t=np.array(target[f-1],copy=True)
 for i,a,b,w in mapping:t[i]=target[f-1,a]*(1-w)+target[f-1,b]*w
 root_error=max(root_error,float(np.max(np.abs(x[fix]-t[fix]))));finite=finite and bool(np.isfinite(x).all());length_max=max(length_max,float(np.max(np.abs(np.linalg.norm(x[edges+1]-x[edges],axis=1)/rest-1))))
result=dict(frames=200,crc_pass=True,finite=finite,fixed_point_max_error=root_error,visible_length_error_max=length_max,visible_points=len(initial),strands=len(off)-1)
(d/'all_frames_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
