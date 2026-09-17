"""Geometric invariants and locality, independent of ACES time integration."""
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'extension'))
from native import Solver, parameters

class LocalFK(unittest.TestCase):
    def make(self, near=False, reverse=False):
        z=[.20,.20,.18,.14,.0001 if near else .06,-.04,-.12]
        x=np.c_[np.arange(7)*.05,np.zeros(7),z].astype(np.float32)
        safe=x.copy();safe[:,1]=2;safe[:,2]=.3
        both=np.concatenate([x,safe]);fixed=np.zeros(14,np.uint8);fixed[[0,1,7,8]]=1
        p=parameters();p.update(mesh_contact_mode=2,gravity=0)
        s=Solver(both,[0,7,14],fixed,p,max_colliders=0)
        body=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],np.float32)
        tri=np.array([[0,1,2],[0,2,3]])
        if reverse:tri=tri[:,::-1]
        s.set_mesh(body,tri)
        return s,both

    def test_local_repair_keeps_prefix_length_and_healthy_strand(self):
        for reverse in [False,True]:
            s,before=self.make(reverse=reverse)
            s.probe(5)
            np.testing.assert_array_equal(s.x[:5],before[:5])
            np.testing.assert_array_equal(s.x[7:],before[7:])
            np.testing.assert_allclose(np.linalg.norm(np.diff(s.x[:7],axis=0),axis=1),np.linalg.norm(np.diff(before[:7],axis=0),axis=1),atol=1e-7,rtol=2e-6)
            self.assertGreater(float(s.x[:7,2].min()),.000189)
            self.assertLessEqual(s.fk_data()[0,2],1)
            self.assertEqual(s.fk_data()[0,3],0)
            self.assertEqual(s.fk_data()[1,1],0)
            repaired=s.x.copy();s.probe(5)
            np.testing.assert_array_equal(s.x,repaired)
            s.close()

    def test_near_surface_point_uses_previous_safe_joint(self):
        s,before=self.make(near=True)
        s.probe(5)
        np.testing.assert_array_equal(s.x[:4],before[:4])
        self.assertGreater(float(s.x[:7,2].min()),.000189)
        self.assertLessEqual(s.fk_data()[0,2],1)
        self.assertEqual(s.fk_data()[0,3],0)
        s.close()

    def test_local_contact_does_not_rotate_long_clear_tail(self):
        x=np.array([[-.10,0,.50],[-.08,0,.48],[-.03,0,.45],[-.005,0,.42],[.005,0,.40],[.005,0,.2],[.005,0,0]],np.float32)
        p=parameters();p.update(mesh_contact_mode=2,gravity=0)
        s=Solver(x,[0,len(x)],np.array([1,1,0,0,0,0,0],np.uint8),p,max_colliders=0)
        body=np.array([[0,-1,-1],[0,1,-1],[0,1,1],[0,-1,1]],np.float32)
        s.set_mesh(body,[[0,1,2],[0,2,3]]);s.probe(5)
        np.testing.assert_array_equal(s.x[:4],x[:4])
        self.assertLess(float(s.x[:,0].max()),-.000189)
        self.assertLess(float(np.linalg.norm(s.x-x,axis=1).max()),.02)
        np.testing.assert_allclose(np.diff(s.x[4:],axis=0),np.diff(x[4:],axis=0),atol=1e-7)
        self.assertEqual(s.fk_data()[0,3],0);s.close()

    def test_moving_body_resident_matches_streamed_with_two_pins(self):
        p=parameters();p.update(mesh_contact_mode=2,gravity=9.80665,length_passes=8)
        x=np.c_[np.arange(8)*.025,np.zeros(8),np.linspace(.15,.03,8)].astype(np.float32)
        fixed=np.array([1,1,0,0,0,0,0,0],np.uint8)
        body=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],np.float32)
        vertices=np.stack([body+np.array([0,0,f*.001],np.float32) for f in range(12)])
        targets=np.repeat(x[None],12,axis=0)
        s=Solver(x,[0,8],fixed,p,max_colliders=0);r=Solver(x,[0,8],fixed,p,max_colliders=0)
        for obj in [s,r]:obj.set_mesh(body,[[0,1,2],[0,2,3]])
        r.set_animation(targets,vertices)
        for f in range(12):
            s.step(targets[f],mesh_previous=vertices[max(0,f-1)],mesh_next=vertices[f]);r.step_animation(f)
            np.testing.assert_array_equal(s.x,r.x)
            np.testing.assert_array_equal(s.x[:2],x[:2])
            self.assertTrue(np.isfinite(s.v).all())
            self.assertGreater(float(s.x[2:,2].min()),f*.001-.000001)
        s.close();r.close()

if __name__=='__main__':unittest.main()
