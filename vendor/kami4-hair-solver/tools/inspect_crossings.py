import sys,json
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'));import cache
run=sys.argv[sys.argv.index('--')+1];d=ROOT/'outputs'/run;m=cache.load(d);x=cache.read(d,23,m['topology_hash'],m['parameter_hash'],m['points']);v=np.load(ROOT/'outputs/input/vertices.npy',mmap_mode='r')[22];tri=np.load(ROOT/'outputs/input/triangles.npy');bv=BVHTree.FromPolygons(v.tolist(),tri.tolist(),all_triangles=True)
r=json.loads((d/'contact_check.json').read_text())['23'];out=[]
for i in r['edges'][:8]:
 p=x[i];q=x[i+1];delta=q-p;length=float(np.linalg.norm(delta));direction=Vector(delta/length);hits=[];u=0.
 for k in range(20):
  co,n,idx,dist=bv.ray_cast(Vector(p)+direction*u,direction,length-u)
  if idx is None:break
  u+=dist;hits.append(dict(t=u/length,side=float(n.dot(direction)),triangle=idx));u+=1e-7
 samples=[]
 for t in np.linspace(0,1,51):
  pt=Vector(p)*(1-t)+Vector(q)*t;co,n,idx,dist=bv.find_nearest(pt);samples.append(float((pt-co).dot(n)))
 out.append(dict(edge=i,p=p.tolist(),q=q.tolist(),hits=hits,min_sample_signed=min(samples)))
print(json.dumps(out,indent=2))
(d/'crossing_details.json').write_text(json.dumps(out,indent=2))
