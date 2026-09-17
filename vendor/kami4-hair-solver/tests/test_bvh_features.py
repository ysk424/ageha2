import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
from native import Solver,parameters
from topology import extend

class Features(unittest.TestCase):
    def test_invisible_tail_preserves_input_and_two_pins(self):
        x=np.c_[np.linspace(0,.05,11),np.zeros((11,2))].astype(np.float32)
        fixed=np.r_[np.ones(2,np.uint8),np.zeros(9,np.uint8)]
        t=extend(x,[0,11],fixed,.2,.01)
        np.testing.assert_array_equal(t['positions'][t['visible_indices']],x)
        np.testing.assert_array_equal(t['fixed'][:11],fixed)
        self.assertEqual(t['fixed'].sum(),2)
        self.assertTrue(np.all(t['contact_enabled'][11:]==0))
        self.assertAlmostEqual(float(np.linalg.norm(np.diff(t['positions'],axis=0),axis=1).sum()),.2,places=6)

    def make(self,z):
        p=parameters();p.update(gravity=0.,damping=0.,mesh_contact_mode=1,length_passes=8)
        x=np.array([[-.1,0,z],[.1,0,z]],np.float32)
        return Solver(x,[0,2],np.zeros(2,np.uint8),p,max_colliders=0)

    def test_segment_interior_hits_both_sides_and_both_windings(self):
        body=np.array([[-.03,-.03,0],[.03,-.03,0],[0,.03,0]],np.float32)
        for side in [-1,1]:
            for winding in [[0,1,2],[2,1,0]]:
                s=self.make(side*.01);s.set_mesh(body,[winding]);v=np.zeros_like(s.x);v[:,2]=-side
                s.set_state(s.x,v);s.step(mesh_previous=body,mesh_next=body)
                # Both endpoints lie outside the triangle footprint. Its interior must stop the strand.
                self.assertGreater(side*float(s.x[:,2].mean()),.0001)
                self.assertTrue(np.isfinite(s.x).all());s.close()

    def test_moving_body_and_resident_path_match(self):
        body=np.array([[-.03,-.03,-.02],[.03,-.03,-.02],[0,.03,-.02]],np.float32)
        end=body.copy();end[:,2]=.02
        s=self.make(.001);r=self.make(.001)
        for obj in [s,r]:obj.set_mesh(body,[[0,1,2]])
        targets=np.stack([s.x,s.x]);vertices=np.stack([body,end])
        r.set_animation(targets,vertices)
        for frame in range(2):
            s.step(targets[frame],mesh_previous=vertices[max(0,frame-1)],mesh_next=vertices[frame]);r.step_animation(frame)
            np.testing.assert_array_equal(s.x,r.x)
        self.assertGreater(float(s.x[:,2].mean()),.0201)
        s.close();r.close()

if __name__=='__main__':unittest.main()
