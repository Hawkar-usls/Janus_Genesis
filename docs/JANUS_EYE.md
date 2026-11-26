# JANUS EYE — spatial perception organ

Research module of PLA Janus Genesis, based on the archived PLA engine. It does not modify the original print pipeline or game main.

Install: `pip install -e . scipy plotly`. Run `python -m janus_genesis.spatial_eye scene.npz scene.json out`.

Input: NPZ with regular ascending 1D x/y axes, 2D height and optional co-registered scalar fields; JSON manifest schema janus.eye.heightfield.v1. Required source SHA-256, explicit frame, units (m/km/mm for geometric axes), authority (MEASURED/MODELLED/INTERPOLATED/SIMULATED/DERIVED/UNKNOWN), provenance. Each scalar field declares unit, frame, authority and provenance. Optional sigma_m, depression_threshold_m and named nodes in metric coordinates. Coordinate alignment is caller's responsibility; matching frame declarations do not prove alignment.

Output: surface_m.ply (open scientific surface, no print base), scene_layers.npz, scene_receipt.json (machine-readable source, geometry, named locations and regions), offline eye.html with rotatable 3D view and scalar fields mapped to colour only. Missing cells remain unknown. Numerical derivatives use physical coordinates, not exaggerated visual geometry.

The first implementation is a heightfield organ, not a general SLAM, video, point-cloud, or volumetric reconstruction engine. Scene receipts are intended for a future Memory Cortex adapter, not automatically ingested. A model is never promoted to measured data. No claim of sensor access or autonomous spatial awareness.

KUSTO integration uses a pinned data receipt and a pinned Genesis commit; the COSMOS workflow owns the data handoff. Other JANUS organs can use the same interface with their own coordinate frames and units.
