#pragma once

#include <cuda_runtime.h>
#include <cmath>

namespace kami {
namespace cuda_geometry {

struct DVec3 {
    double x, y, z;
};

__host__ __device__ inline DVec3 make_vec(double x = 0.0, double y = 0.0, double z = 0.0)
{
    return {x, y, z};
}

__host__ __device__ inline DVec3 operator+(DVec3 a, DVec3 b) { return {a.x+b.x, a.y+b.y, a.z+b.z}; }
__host__ __device__ inline DVec3 operator-(DVec3 a, DVec3 b) { return {a.x-b.x, a.y-b.y, a.z-b.z}; }
__host__ __device__ inline DVec3 operator*(DVec3 a, double s) { return {a.x*s, a.y*s, a.z*s}; }
__host__ __device__ inline DVec3 operator*(double s, DVec3 a) { return a*s; }
__host__ __device__ inline DVec3 operator/(DVec3 a, double s) { return a*(1.0/s); }
__host__ __device__ inline double dot(DVec3 a, DVec3 b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
__host__ __device__ inline DVec3 cross(DVec3 a, DVec3 b)
{
    return {a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x};
}
__host__ __device__ inline double norm2(DVec3 a) { return dot(a,a); }
__host__ __device__ inline double norm(DVec3 a) { return sqrt(norm2(a)); }
__host__ __device__ inline DVec3 min_vec(DVec3 a, DVec3 b)
{
    return {fmin(a.x,b.x),fmin(a.y,b.y),fmin(a.z,b.z)};
}
__host__ __device__ inline DVec3 max_vec(DVec3 a, DVec3 b)
{
    return {fmax(a.x,b.x),fmax(a.y,b.y),fmax(a.z,b.z)};
}

struct ClosestPair { double distance,t; DVec3 bary; };
__host__ __device__ inline DVec3 closest_point_triangle(DVec3 p,DVec3 a,DVec3 b,DVec3 c,DVec3&bary) {
    const DVec3 ab=b-a,ac=c-a,ap=p-a;const double d1=dot(ab,ap),d2=dot(ac,ap);
    if(d1<=0&&d2<=0){bary=make_vec(1,0,0);return a;}const DVec3 bp=p-b;
    const double d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3){bary=make_vec(0,1,0);return b;}
    const double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0){double v=d1/(d1-d3);bary=make_vec(1-v,v,0);return a+ab*v;}
    const DVec3 cp=p-c;const double d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6){bary=make_vec(0,0,1);return c;}
    const double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0){double w=d2/(d2-d6);bary=make_vec(1-w,0,w);return a+ac*w;}
    const double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0){double w=(d4-d3)/((d4-d3)+(d5-d6));bary=make_vec(0,1-w,w);return b+(c-b)*w;}
    const double inv=1.0/(va+vb+vc),v=vb*inv,w=vc*inv;bary=make_vec(1-v-w,v,w);return a+ab*v+ac*w;
}
__host__ __device__ inline void consider_segment(DVec3 p1,DVec3 q1,DVec3 p2,DVec3 q2,double&best,double&bs,double&bt) {
    const DVec3 d1=q1-p1,d2=q2-p2,r=p1-p2;const double a=dot(d1,d1),e=dot(d2,d2),f=dot(d2,r);double s=0,t=0;
    if(a<=1e-14&&e<=1e-14){}else if(a<=1e-14)t=fmin(1.0,fmax(0.0,f/e));else{const double c=dot(d1,r);
        if(e<=1e-14)s=fmin(1.0,fmax(0.0,-c/a));else{const double b=dot(d1,d2),den=a*e-b*b;if(den!=0)s=fmin(1.0,fmax(0.0,(b*f-c*e)/den));t=(b*s+f)/e;
            if(t<0){t=0;s=fmin(1.0,fmax(0.0,-c/a));}else if(t>1){t=1;s=fmin(1.0,fmax(0.0,(b-c)/a));}}}
    const double d=norm((p1+d1*s)-(p2+d2*t));if(d<best){best=d;bs=s;bt=t;}
}
__host__ __device__ inline ClosestPair closest_segment_triangle(DVec3 p0,DVec3 p1,DVec3 a,DVec3 b,DVec3 c) {
    // Endpoint/edge distances alone miss a segment piercing the face interior.
    // Reject same-side endpoints before computing the plane intersection.
    const DVec3 ab=b-a,ac=c-a,normal=cross(ab,ac);
    const double side0=dot(normal,p0-a),side1=dot(normal,p1-a);
    if((side0<=0.0&&side1>=0.0)||(side0>=0.0&&side1<=0.0)){
        const double denominator=side0-side1;
        if(denominator!=0.0){
            const double t=side0/denominator;
            const DVec3 hit=p0+(p1-p0)*t,relative=hit-a;
            const double normal_squared=norm2(normal);
            if(normal_squared>0.0){
                const double u=dot(cross(relative,ac),normal)/normal_squared;
                const double v=dot(cross(ab,relative),normal)/normal_squared;
                if(u>=0.0&&v>=0.0&&u+v<=1.0)return {0.0,t,make_vec(1.0-u-v,u,v)};
            }
        }
    }
    ClosestPair out{1.0e300,0,make_vec(1,0,0)};DVec3 bary,cp=closest_point_triangle(p0,a,b,c,bary);double d=norm(p0-cp);
    if(d<out.distance)out={d,0,bary};cp=closest_point_triangle(p1,a,b,c,bary);d=norm(p1-cp);if(d<out.distance)out={d,1,bary};
    DVec3 tv[3]{a,b,c};for(int e=0;e<3;++e){double best=out.distance,s=0,t=0;consider_segment(p0,p1,tv[e],tv[(e+1)%3],best,s,t);
        if(best<out.distance){out.distance=best;out.t=s;out.bary=make_vec();if(e==0){out.bary.x=1-t;out.bary.y=t;}else if(e==1){out.bary.y=1-t;out.bary.z=t;}else{out.bary.z=1-t;out.bary.x=t;}}}
    return out;
}

} // namespace cuda_geometry
} // namespace kami
