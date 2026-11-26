"""JANUS EYE: coordinate-aware, non-mutating spatial perception for registered heightfields.

Run: python -m janus_genesis.spatial_eye scene.npz scene.json output_directory
Optional: install scipy and plotly for analysis and offline interactive visualization.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from pathlib import Path

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter, label
from scipy.stats import spearmanr

from janus_genesis.mesh_ops import metrics

AUTHORITIES = {"MEASURED", "MODELLED", "INTERPOLATED", "SIMULATED", "DERIVED", "UNKNOWN"}
UNITS_TO_M = {"m": 1., "km": 1000., "mm": .001}

def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False)+"\n", encoding="utf-8")

def validate_grid(x, y, z):
    if x.ndim != 1 or y.ndim != 1 or z.shape != (len(y),len(x)):
        raise ValueError("expected 1D ascending coordinate axes and 2D heightfield")
    if min(len(x),len(y)) < 5 or z.size > 2_000_000:
        raise ValueError("grid size outside supported range")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.isinf(z).any():
        raise ValueError("nonfinite axes or infinite height")
    for a in (x,y):
        d=np.diff(a)
        if not np.all(d>0) or not np.allclose(d,d[0],rtol=1e-6,atol=1e-12):
            raise ValueError("regular ascending axes required")
    if not np.isfinite(z).any():
        raise ValueError("no valid heights")

def derivatives(z, dx, dy):
    zy,zx=np.gradient(z,dy,dx,edge_order=2)
    zyy,zyx=np.gradient(zy,dy,dx,edge_order=2)
    zxy,zxx=np.gradient(zx,dy,dx,edge_order=2)
    cross=(zxy+zyx)/2
    slope=np.degrees(np.arctan(np.hypot(zx,zy)))
    lap=zxx+zyy
    mean=((1+zy**2)*zxx-2*zx*zy*cross+(1+zx**2)*zyy)/(2*(1+zx*zx+zy*zy)**1.5)
    gauss=(zxx*zyy-cross**2)/(1+zx*zx+zy*zy)**2
    return slope,lap,mean,gauss

def smooth(z, sigma_yx):
    if max(sigma_yx)==0:
        return z.copy()
    valid=np.isfinite(z)
    if valid.all():
        return gaussian_filter(z,sigma_yx,mode="nearest")
    w=gaussian_filter(valid.astype(float),sigma_yx,mode="constant")
    n=gaussian_filter(np.where(valid,z,0.),sigma_yx,mode="constant")
    # Do not impute source gaps; additionally exclude poorly supported neighborhoods.
    return np.divide(n,w,out=np.full_like(n,np.nan),where=(w>=.95)&valid)

def depression_depth(z):
    """Priority flood on complete grids; do not claim closure across unknown cells."""
    if not np.isfinite(z).all():
        return None
    ny,nx=z.shape
    filled=z.copy(); seen=np.zeros(z.shape,bool); heap=[]
    for j in range(ny):
        for i in range(nx):
            if j in (0,ny-1) or i in (0,nx-1):
                seen[j,i]=True;heapq.heappush(heap,(float(z[j,i]),j,i))
    while heap:
        h,j,i=heapq.heappop(heap)
        for dj in (-1,0,1):
            for di in (-1,0,1):
                a,b=j+dj,i+di
                if 0<=a<ny and 0<=b<nx and not seen[a,b]:
                    seen[a,b]=True; hh=max(h,float(z[a,b]))
                    filled[a,b]=hh;heapq.heappush(heap,(hh,a,b))
    return filled-z

def stats(v):
    a=np.asarray(v)[np.isfinite(v)]
    return {"count":int(a.size),"min":float(a.min()),"median":float(np.median(a)),"max":float(a.max())} if a.size else {"count":0}

def geometry_mesh(x,y,z):
    X,Y=np.meshgrid(x,y)
    finite=np.isfinite(z).ravel()
    verts=np.column_stack([X.ravel(),Y.ravel(),z.ravel()])
    faces=[];ny,nx=z.shape
    for j in range(ny-1):
        for i in range(nx-1):
            a=j*nx+i;b=a+1;c=a+nx;d=c+1
            for f in ((a,b,d),(a,d,c)):
                if finite[list(f)].all():faces.append(f)
    if not faces:raise ValueError("no supported triangles")
    mapping=np.full(z.size,-1,int);mapping[finite]=np.arange(finite.sum())
    mesh=trimesh.Trimesh(vertices=verts[finite],faces=mapping[np.asarray(faces)],process=False)
    mesh.remove_unreferenced_vertices()
    return mesh

def region_records(depth,x,y,threshold):
    labels,n=label(depth>=threshold,structure=np.ones((3,3),int))
    dx,dy=x[1]-x[0],y[1]-y[0]
    regions=[]
    for k in range(1,n+1):
        j,i=np.where(labels==k)
        regions.append({"region_id":f"depression_{k}","cell_count":len(i),
          "cell_area_m2":float(len(i)*dx*dy),"max_fill_depth_m":float(depth[j,i].max()),
          "centroid_xy_m":[float(np.mean(x[i])),float(np.mean(y[j]))],
          "bbox_xy_m":[float(x[i].min()),float(y[j].min()),float(x[i].max()),float(y[j].max())]})
    return labels,regions

def analyze(npz, manifest, out, render=True):
    npz,manifest,out=map(Path,(npz,manifest,out))
    meta=json.loads(manifest.read_text(encoding="utf-8"))
    if meta.get("schema")!="janus.eye.heightfield.v1":raise ValueError("unsupported scene schema")
    if digest(npz)!=meta["sha256"]:raise ValueError("source digest mismatch")
    if meta["authority"] not in AUTHORITIES or not isinstance(meta["frame"],str) or not meta["frame"].strip():
        raise ValueError("explicit source authority and coordinate frame required")
    if not meta.get("provenance"):raise ValueError("source provenance required")
    xy_scale=UNITS_TO_M[meta["xy_unit"]];z_scale=UNITS_TO_M[meta["height_unit"]]
    with np.load(npz,allow_pickle=False) as data:
        x=np.asarray(data["x"],float)*xy_scale;y=np.asarray(data["y"],float)*xy_scale
        z=np.asarray(data["height"],float)*z_scale
        validate_grid(x,y,z)
        fields={}
        for name,spec in meta.get("fields",{}).items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}",name):raise ValueError("invalid field name")
            if spec["authority"] not in AUTHORITIES or not spec.get("unit") or not spec.get("provenance"):
                raise ValueError("field metadata incomplete")
            if spec.get("frame")!=meta["frame"]:raise ValueError("field frame mismatch")
            f=np.asarray(data[name],float)
            if f.shape!=z.shape or np.isinf(f).any():raise ValueError("field grid mismatch")
            fields[name]=f
    dx=float(x[1]-x[0]);dy=float(y[1]-y[0])
    sigmas=meta.get("sigma_m",[0,2*max(dx,dy),4*max(dx,dy)])
    if not sigmas or len(sigmas)>8 or any(not np.isfinite(s) or s<0 or s>max(np.ptp(x),np.ptp(y)) for s in sigmas):
        raise ValueError("invalid scale set")
    threshold=float(meta.get("depression_threshold_m",max(dx,dy)*.01))
    if not np.isfinite(threshold) or threshold<=0:raise ValueError("invalid depression threshold")
    out.mkdir(parents=True,exist_ok=True)
    mesh=geometry_mesh(x,y,z)
    # Existing PLA Genesis geometry inspector reused; convert its units-label convention explicitly.
    mm=mesh.copy();mm.apply_scale(1000)
    mesh_report=metrics(mm).to_dict()
    mesh.export(out/"surface_m.ply")
    report={"schema":"janus.eye.scene_receipt.v1","scene_id":meta["scene_id"],"source_sha256":meta["sha256"],
      "manifest_sha256":digest(manifest),"authority":meta["authority"],"frame":meta["frame"],
      "provenance":meta["provenance"],"units":{"coordinates":"m","height":"m","curvature":"1/m"},
      "height":stats(z),"coverage_fraction":float(np.isfinite(z).mean()),"sampling_m":[dx,dy],
      "mesh":{"file":"surface_m.ply","vertex_unit":"m","sha256":digest(out/"surface_m.ply"),"pla_genesis_metrics_mm":mesh_report,
        "surface_only":True,"closed_solid_required":False,"source_geometry_mutated":False},
      "scales":[],"field_associations":{},"regions":[],"nodes":[],
      "claim_ceiling":"DESCRIPTIVE_GEOMETRY_NO_CAUSAL_OR_SENSOR_UPGRADE"}
    layers={"x_m":x,"y_m":y,"height_m":z}
    for name,f in fields.items():
        layers["field_"+name]=f
        q=np.isfinite(z)&np.isfinite(f)
        rho=float(spearmanr(z[q],f[q]).statistic) if q.sum()>=3 and np.ptp(z[q])>0 and np.ptp(f[q])>0 else None
        report["field_associations"][name]={"unit":meta["fields"][name]["unit"],"authority":meta["fields"][name]["authority"],
           "provenance":meta["fields"][name]["provenance"],"paired_cells":int(q.sum()),"spearman_rho":rho,"independent_samples":False}
    for k,s in enumerate(sigmas):
        sm=smooth(z,(float(s)/dy,float(s)/dx));sl,lap,mean,gauss=derivatives(sm,dx,dy)
        layer={"slope_deg":sl,"laplacian_per_m":lap,"mean_curvature_per_m":mean,"gaussian_curvature_per_m2":gauss}
        depth=depression_depth(sm)
        entry={"scale_sigma_m":float(s),"slope_deg":stats(sl),"laplacian_per_m":stats(lap),"mean_curvature_per_m":stats(mean),"gaussian_curvature_per_m2":stats(gauss),"depression_status":"BLOCKED_INCOMPLETE_GRID" if depth is None else "FINITE_WINDOW_PROXY"}
        if depth is not None:
            labels,regions=region_records(depth,x,y,threshold)
            layer["fill_depth_m"]=depth;layer["depression_labels"]=labels
            for reg in regions:
                reg["scale_sigma_m"]=float(s);reg["region_id"]=f"s{k}_"+reg["region_id"]
            report["regions"].extend(regions);entry["region_count"]=len(regions)
        for name,v in layer.items():layers[f"s{k}_{name}"]=v
        report["scales"].append(entry)
    for node in meta.get("nodes",[]):
        px,py=map(float,node["xy_m"])
        if not (x[0]<=px<=x[-1] and y[0]<=py<=y[-1]):raise ValueError("node outside scene")
        i=int(np.argmin(abs(x-px)));j=int(np.argmin(abs(y-py)))
        def val(a,j=j,i=i):return float(a[j,i]) if np.isfinite(a[j,i]) else None
        report["nodes"].append({"id":node["id"],"requested_xy_m":[px,py],"sample_xy_m":[float(x[i]),float(y[j])],
           "height_m":val(z),"fields":{name:val(a) for name,a in fields.items()},
           "scales":[{"sigma_m":float(s),**{name:val(layers[f"s{k}_{name}"]) for name in ("slope_deg","mean_curvature_per_m","fill_depth_m") if f"s{k}_{name}" in layers}} for k,s in enumerate(sigmas)]})
    np.savez_compressed(out/"scene_layers.npz",**layers)
    report["layers_sha256"]=digest(out/"scene_layers.npz")
    report["limitations"]=["Heightfield only; not unrestricted volumetric perception","No invented observations across missing cells","Depression closure is a finite-window proxy; complete grids use nearest-edge smoothing","Field correlation is descriptive, not a causal or independent test","Source authority is declared, not independently authenticated"]
    if render:
        import plotly.graph_objects as go
        fig=go.Figure()
        fig.add_trace(go.Surface(x=x,y=y,z=z,name="height",colorscale="Viridis",connectgaps=False,colorbar={"title":"height (m)"}))
        buttons=[{"label":"Height (m)","method":"update","args":[{"surfacecolor":[z],"colorscale":["Viridis"],"cmin":[float(np.nanmin(z))],"cmax":[float(np.nanmax(z))],"colorbar":[{"title":"height (m)"}]}]}]
        for name,f in fields.items():
            if np.isfinite(f).any():
                lo=float(np.nanmin(f));hi=float(np.nanmax(f))
                buttons.append({"label":name+" ("+meta["fields"][name]["unit"]+")","method":"update","args":[{"surfacecolor":[f],"colorscale":["RdBu"],"cmin":[lo],"cmax":[hi],"colorbar":[{"title":meta["fields"][name]["unit"]}]}]})
        fig.update_layout(title="JANUS EYE | "+meta["authority"]+" | "+meta["scene_id"],scene={"xaxis_title":"x (m)","yaxis_title":"y (m)","zaxis_title":"height (m)","aspectmode":"data"},updatemenus=[{"buttons":buttons,"x":0,"y":1.1}])
        fig.write_html(out/"eye.html",include_plotlyjs=True,full_html=True)
        report["interactive_view"]={"file":"eye.html","sha256":digest(out/"eye.html"),"field_values_are_colors_not_height":True}
    write(out/"scene_receipt.json",report)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("npz");p.add_argument("manifest");p.add_argument("output");p.add_argument("--no-render",action="store_true")
    a=p.parse_args()
    print(json.dumps(analyze(a.npz,a.manifest,a.output,not a.no_render),indent=2,allow_nan=False))

if __name__=="__main__":main()
