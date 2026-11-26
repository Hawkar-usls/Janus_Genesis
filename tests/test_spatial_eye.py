import json

import numpy as np
import pytest

from janus_genesis.spatial_eye import analyze, depression_depth, derivatives, digest, smooth

def scene(tmp_path, z, x=None, field=None):
    if x is None: x=np.arange(z.shape[1],dtype=float)
    y=np.arange(z.shape[0],dtype=float)
    fields={} if field is None else {"gravity": {"unit":"mGal","authority":"SIMULATED","frame":"local metric","provenance":"analytic control"}}
    p=tmp_path/"scene.npz"
    np.savez_compressed(p,x=x,y=y,height=z,**({} if field is None else {"gravity":field}))
    m=tmp_path/"scene.json"
    m.write_text(json.dumps({"schema":"janus.eye.heightfield.v1","scene_id":"analytic","sha256":digest(p),"authority":"SIMULATED","frame":"local metric","xy_unit":"m","height_unit":"m","provenance":"analytic control","fields":fields,"sigma_m":[0,1],"depression_threshold_m":1,"nodes":[{"id":"center","xy_m":[4,4]}]}))
    return p,m

def test_plane_and_curvature():
    x,y=np.meshgrid(np.arange(9.),np.arange(9.))
    slope,lap,_mean,gauss=derivatives(.1*x,1,1)
    assert np.allclose(slope,np.degrees(np.arctan(.1)))
    assert np.max(np.abs(lap))<1e-12
    assert np.max(np.abs(gauss))<1e-12
    assert np.allclose(derivatives(.01*(x*x+y*y),1,1)[1],.04)

def test_closed_and_open():
    z=np.zeros((9,9));z[2:7,2:7]=-10
    assert depression_depth(z)[4,4]==10
    z[4,:4]=-10
    assert depression_depth(z)[4,4]==0

def test_scene_and_field_geometry(tmp_path):
    z=np.zeros((9,9));z[2:7,2:7]=-10
    p,m=scene(tmp_path,z,field=z*2)
    r=analyze(p,m,tmp_path/"out",render=True)
    assert r["authority"]=="SIMULATED"
    assert r["nodes"][0]["height_m"]==-10
    assert r["nodes"][0]["scales"][0]["fill_depth_m"]==10
    assert r["field_associations"]["gravity"]["spearman_rho"]==pytest.approx(1)
    assert r["mesh"]["source_geometry_mutated"] is False
    assert r["mesh"]["pla_genesis_metrics_mm"]["faces"]==128
    assert (tmp_path/"out"/"eye.html").stat().st_size>10000
    with np.load(tmp_path/"out"/"scene_layers.npz") as a:
        assert np.array_equal(a["height_m"],z)
        assert np.array_equal(a["field_gravity"],z*2)

def test_missing_data(tmp_path):
    z=np.zeros((9,9));z[4,4]=np.nan
    p,m=scene(tmp_path,z)
    r=analyze(p,m,tmp_path/"out",render=False)
    assert r["coverage_fraction"]<1
    assert r["nodes"][0]["height_m"] is None
    assert all(s["depression_status"]=="BLOCKED_INCOMPLETE_GRID" for s in r["scales"])
    assert np.isnan(smooth(z,(1,1))[4,4])

def test_digest_rejected(tmp_path):
    p,m=scene(tmp_path,np.zeros((9,9)))
    d=json.loads(m.read_text());d["sha256"]="0"*64;m.write_text(json.dumps(d))
    with pytest.raises(ValueError,match="digest"):analyze(p,m,tmp_path/"out",render=False)

def test_frame_rejected(tmp_path):
    p,m=scene(tmp_path,np.zeros((9,9)),field=np.ones((9,9)))
    d=json.loads(m.read_text());d["fields"]["gravity"]["frame"]="other";m.write_text(json.dumps(d))
    with pytest.raises(ValueError,match="frame"):analyze(p,m,tmp_path/"out",render=False)

def test_bad_axis_rejected(tmp_path):
    p,m=scene(tmp_path,np.zeros((9,9)),x=np.arange(9.)[::-1])
    with pytest.raises(ValueError,match="ascending"):analyze(p,m,tmp_path/"out",render=False)
