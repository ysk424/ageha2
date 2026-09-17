// Residual contact repair only. The ACES bending/length solve is unchanged.
// One thread owns one strand; each repair keeps the safe prefix stationary.
struct FkHit { int edge = -1, id = -1; float t = 2; V point, normal, bary; };

__device__ FkHit fk_edge_hit(Device d, int edge, uint32_t &queries) {
    ++queries;
    FkHit hit;
    V p = d.x[edge], q = d.x[edge + 1];
    float radius = d.cfg.radius + d.cfg.contact_tolerance;
    V pad(radius, radius, radius), low = minv(p,q)-pad, high = maxv(p,q)+pad;
    int stack[64], top = 0; stack[top++] = 0;
    while (top) {
        Node node = d.nodes[stack[--top]];
        if (!boxes_overlap(low,high,node.lo,node.hi) || !segment_box(p,q,node.lo,node.hi,radius)) continue;
        if (!node.count) {
            if (top + 2 > 64) { d.diag[edge].overflow = 1; break; }
            stack[top++] = node.left; stack[top++] = node.right; continue;
        }
        for (int k=0;k<node.count;++k) {
            int id=d.order[node.first+k]; Tri tr=d.tris[id];
            V a=d.mesh[tr.a], b=d.mesh[tr.b], c=d.mesh[tr.c];
            if (!segment_box(p,q,minv(a,minv(b,c)),maxv(a,maxv(b,c)),radius)) continue;
            auto pair=sg::closest_segment_triangle(geo(p),geo(q),geo(a),geo(b),geo(c));
            if (pair.distance >= radius || pair.t > hit.t) continue;
            V n=unit(cross(b-a,c-a));
            if (norm(n)<.5f) continue;
            V bary((float)pair.bary.x,(float)pair.bary.y,(float)pair.bary.z);
            V surface=a*bary.x+b*bary.y+c*bary.z;
            // The first crossing from the stationary root prefix determines the safe side.
            // Intentionally two-sided, including reversed winding and open cards.
            if (dot(p-surface,n)<0) n=-n;
            if (fminf(dot(p-surface,n),dot(q-surface,n)) >= radius-1e-7f) continue;
            hit={edge,id,(float)pair.t,surface,n,bary};
        }
    }
    return hit;
}

__device__ V fk_rotate(V value, V axis, float sine, float cosine) {
    return value*cosine + cross(axis,value)*sine + axis*(dot(axis,value)*(1-cosine));
}

__global__ void repair_local_fk(Device d) {
    int strand=blockIdx.x*blockDim.x+threadIdx.x;
    if (strand>=d.s) return;
    int a=d.offsets[strand], b=d.offsets[strand+1];
    for(int i=a;i<b;++i) d.fk_correction[i]={};
    if (!d.nt) return;
    uint32_t *stats=d.fk_diag+6*strand;
    stats[3]=0;
    int first=a;
    while(first+1<b && d.fixed[first+1]) ++first;
    // Arbitrary interior pins are not moved by this pass.
    int end=b;
    for(int i=first+1;i<b;++i) if(d.fixed[i]) {end=i;break;}
    int visible=first;
    while(visible+1<end && (!d.contact_enabled || (d.contact_enabled[visible] && d.contact_enabled[visible+1]))) ++visible;
    if(visible<=first) return;
    int cursor=first, repairs=0, budget=visible-first;
    const float clearance=d.cfg.radius+d.cfg.contact_tolerance+2e-6f;
    while(cursor<visible) {
        FkHit hit=fk_edge_hit(d,cursor,stats[0]);
        if(hit.id<0) {++cursor;continue;}
        stats[5]=1;
        if(repairs>=budget) {stats[3]=1;break;}
        int pivot=cursor;
        while(pivot>first && dot(d.x[pivot]-hit.point,hit.normal)<clearance) --pivot;
        float parent_distance=dot(d.x[pivot]-hit.point,hit.normal);
        if(parent_distance<clearance-1e-7f) {stats[3]=1;break;}
        // Build the unrotated rest-length FK chain to the colliding endpoint.
        V offset;
        for(int i=pivot;i<=cursor;++i) offset=offset+unit(d.x[i+1]-d.x[i])*d.rest[i];
        float length=norm(offset);
        if(length<1e-8f) {stats[3]=1;break;}
        float wanted=fminf(1.0f,fmaxf(-1.0f,(clearance-parent_distance)/length));
        V from=unit(offset), tangent=from-hit.normal*dot(from,hit.normal);
        if(norm(tangent)<1e-7f) {
            V prior=pivot>a?d.x[pivot]-d.x[pivot-1]:V(1,0,0);
            tangent=prior-hit.normal*dot(prior,hit.normal);
            if(norm(tangent)<1e-7f) tangent=cross(hit.normal,fabsf(hit.normal.x)<.9f?V(1,0,0):V(0,1,0));
        }
        V to=unit(tangent)*sqrtf(fmaxf(0.0f,1-wanted*wanted))+hit.normal*wanted;
        if(dot(from,hit.normal)>=wanted) to=from;
        V rotation=cross(from,to);
        float sine=norm(rotation), cosine=fminf(1.0f,fmaxf(-1.0f,dot(from,to)));
        V axis=sine>1e-8f?rotation/sine:unit(cross(from,fabsf(from.x)<.9f?V(1,0,0):V(0,1,0)));
        V previous_old=d.x[pivot], previous_new=previous_old;
        for(int i=pivot+1;i<end;++i) {
            V old=d.x[i], direction=unit(old-previous_old);
            // Rotate only the repaired block. Descendant rods retain their ACES world
            // directions and are reattached by FK, avoiding long-tail lever amplification.
            V transported=i<=cursor+1?fk_rotate(direction,axis,sine,cosine):direction;
            V next=previous_new+transported*d.rest[i-1];
            V correction=next-old;
            d.fk_correction[i]=d.fk_correction[i]+correction;
            d.x[i]=next;
            previous_old=old; previous_new=next;
            ++stats[4];
        }
        // Geometric displacement is removed from reconstructed velocity; no double support.
        int point=cursor+1;
        Contact &con=d.contacts[point*d.slots+d.slots-1];
        con.id=hit.id; con.n=hit.normal; con.jn=0; con.jt={}; con.support=0; con.mu=d.cfg.friction;
        Tri tr=d.tris[hit.id];
        con.velocity=((d.mesh1[tr.a]-d.mesh0[tr.a])*hit.bary.x+(d.mesh1[tr.b]-d.mesh0[tr.b])*hit.bary.y+(d.mesh1[tr.c]-d.mesh0[tr.c])*hit.bary.z)/d.cfg.dt;
        ++repairs; ++stats[1];
        stats[2]=max(stats[2],(uint32_t)(cursor-pivot));
        cursor=pivot;
    }
}
