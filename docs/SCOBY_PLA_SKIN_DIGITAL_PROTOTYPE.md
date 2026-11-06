# PLA Janus Genesis × SCOBY/PLA × SkinGPT: digital skin coupon

This is an **additive, bounded research module** on the archived PLA Genesis lineage, **not** a change to the separate Genesis video-game main branch.

## Source evidence

- [Canonical STARLI F41 → SCOBY/PLA/SkinGPT bridge](https://github.com/Hawkar-usls/janus-meta-registry/blob/main/data/JANUS-STARLI-F41-SCOBY-PLA-SKINGPT-PHYSICAL-VALIDATION-BRIDGE-2026-11-06-v1.0.json)
- [2026-11-02 NASA-style articulated fabric study](https://github.com/Hawkar-usls/janus-meta-registry/blob/main/data/JANUS-SCOBY-NASA-FABRIC-SKINGPT-INTEGRATED-CONCEPT-2026-11-02-v1.0.json)
- [SCOBY-D0 track](https://github.com/Hawkar-usls/SCOBY-D0) and [private SkinGPT v0.3](https://github.com/Hawkar-usls/SkinGPT)

The F41 PDF supplies **scientific methodology**, not BC/PLA experimental measurements. SkinGPT v0.3 provides a rule-based telemetry prototype (8 NTC zones, one piezo), not a trained GPT model or a validated physical BC sensor-skin.

## Digital generation

```bash
PYTHONPATH=src python -m janus_genesis.scoby_skin_genesis --size 70 --pitch 10 --strut 1.5 --thickness 1.8 --out prototype_out
```

Every successful run writes:

- `B_rigid_pla_lattice_control.stl` — closed raster-extruded **rigid** PLA lattice control specimen for slicer investigation.
- `BC_skin_and_SkinGPT_concept.svg` — a **conceptual** BC overlayer and 8+1 sensor footprints; not a physically manufactured panel.
- `predictions.json` — hash-provenanced geometric fractions/nominal scaffold volume and explicit `null` physical and sensing outcomes.

The generated B **control** is not an articulated chainmail fabric. True articulated C/D arms require a verified/license-cleared source STL, independent clearance/interlock checks, and a separate validated conversion. No NASA STL or unlicensed third-party geometry is embedded here.

Optional: `--skingpt-manifest path/to/session_manifest.json` verifies schema-level provenance for a local SkinGPT v0.3 manifest, copies **only** manifest/log hashes into the output, and does not infer damage statistics or upload private raw logs. A manifest SHA does not prove material or sensor performance.

## GitHub Actions

`.github/workflows/scoby-pla-skin-prototype.yml` is a bounded matrix (three Ubuntu workers: 7, 10, and 14 mm pitch), maximum three workers, maximum ten minutes per job, with seven-day retained result artifacts. It has read-only repository permissions; it never auto-commits, modifies any protected service, consumes LLM tokens, downloads private SkinGPT data, uses the NAS, or exercises hardware.

Run the CI through its supported pull-request trigger. `workflow_dispatch` is available only when the GitHub repository/workflow configuration makes it accessible, typically after the workflow is present on the default branch. The separate **game** default branch must not be replaced with this archived PLA line.

## Evidence boundary and next physical gates

1. Geometry occupancy and volume are deterministic calculations, **not material-strength predictions**.
2. PLA printability needs slicer validation, exact nozzle/layer profile and physical coupon inspection.
3. SCOBY/bacterial-cellulose growth/adhesion must be compared using independent batches: A BC-only, B BC+rigid PLA control, C BC+articulated PLA candidate, D PLA-only, E post-assembled BC+PLA.
4. Blind wet/dry bond, flexion fatigue, hidden interfacial defects, full failure registry and independently labelled SkinGPT readings are mandatory before any effectiveness claims.
5. No food contact, clinical use, certified protective/ballistic function or autonomous repair is asserted.

**No synthetic/model result should ever be reclassified as physical evidence.**
