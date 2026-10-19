"""Portable browser saves must never replace a world during file preview."""

import json
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "site" / "genesis-world-journal.js"


class GenesisBrowserSaveTests(unittest.TestCase):
    def run_journal(self, body):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        harness = r"""
const assert = require('assert/strict'), fs = require('fs'), vm = require('vm'), crypto = require('crypto');
globalThis.crypto = crypto.webcrypto;
const SAVE = 'janus.genesis.world_shell_r0.save.v1', BIRTH = 'janus.genesis.birth_r0_6.v1';
const BACKUP = 'janus.genesis.browser_import.backup.v1', PENDING = 'janus.genesis.birth_r0_6.pending_intent.v1';
const store = new Map(), session = new Map(); let failSaveOnce = false, reloads = 0;
globalThis.localStorage = {
  getItem: key => store.get(key) ?? null,
  setItem: (key, value) => { if (failSaveOnce && key === SAVE) { failSaveOnce = false; throw new Error('QUOTA'); } store.set(key, String(value)); },
  removeItem: key => store.delete(key)
};
globalThis.sessionStorage = {getItem: key => session.get(key) ?? null, setItem: (key, value) => session.set(key, value), removeItem: key => session.delete(key)};
globalThis.location = {reload: () => reloads++};
class Element {
  constructor(tag = 'span') { this.tag = tag; this.children = []; this.textContent = ''; this.hidden = true; this.listeners = new Map(); this.value = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, handler) { this.listeners.set(type, handler); }
  click() { return this.listeners.get('click')?.({target:this}); }
  remove() {}
}
const elements = new Map(['save-status', 'save-export', 'save-import', 'save-import-status', 'save-import-confirm', 'save-import-cancel', 'chronicle-list'].map(id => [id, new Element()]));
const docEvents = new Map();
globalThis.document = {readyState: 'complete', getElementById: id => elements.get(id), createElement: tag => new Element(tag), body: new Element('body'), addEventListener: (type, handler) => docEvents.set(type, handler)};
const digest = text => crypto.createHash('sha256').update(text).digest('hex');
const clone = object => JSON.parse(JSON.stringify(object));
function append(save, type, data) {
  const core = {sequence: save.chronicle_hash_chain.length + 1, type, data, prev: save.chronicle_hash_chain.at(-1)?.event_hash || 'GENESIS'};
  save.chronicle_hash_chain.push({...core, event_hash:digest(JSON.stringify(core))});
}
function world({position = 0, lighthouse = false} = {}) {
  const save = {schema:'janus.genesis.world_shell_save.v1', generator_version:'GENESIS_COMMAND_RUNTIME_R0.3.0', world_id:'GENESIS_ONE_WORLD_R0', world_seed:'genesis-one-world-r0', player_position:{x:position,y:0}, mirror_profile:'ORIGIN', camera_mode:'THIRD_PERSON', camera_heading:0, camera_pitch:-.18, camera_roll:0, camera_distance:8, world_settings:{time:'DAY',fog:.08,weather:'CLEAR'}, discovered_chunk_coordinates:[[0,0]], explicit_world_mutations:[], chronicle_hash_chain:[], birth_state:'BORN_R0_6', birth_seed:'a'.repeat(64), birth_intent_sha256:'b'.repeat(64)};
  append(save, 'GENESIS_BIRTH', {birth_version:'R0.6',birth_seed:save.birth_seed,intent_sha256:save.birth_intent_sha256,intent_length:7,origin_chunk:[0,0]});
  append(save, 'CHUNK_DISCOVERED', {chunk:[0,0],created_at:1700000000000});
  if (lighthouse) {
    save.explicit_world_mutations.push({type:'GENERATED_STRUCTURE',id:'lighthouse-test',concept:'Маяк',structure_kind:'lighthouse',seed:'abcdef01',x:2,y:4,created_at:1700000000001,entry_heading:0,recipe:'KRR_LIGHTHOUSE_R2',interaction_state:{door_open:true,beacon_lit:true},asset_refs:[]});
    append(save,'STRUCTURE_MATERIALIZED',{concept:'Маяк',kind:'lighthouse',x:2,y:4,recipe:'KRR_LIGHTHOUSE_R2',created_at:1700000000001});
    append(save,'LIGHTHOUSE_DOOR_OPENED',{target_id:'lighthouse-test',name:'Маяк',x:2,y:4,created_at:1700000000002});
    append(save,'BEACON_LIT',{target_id:'lighthouse-test',name:'Маяк',x:2,y:4,created_at:1700000000003});
  }
  return save;
}
const initial = world(); store.set(SAVE, JSON.stringify(initial)); store.set(BIRTH, JSON.stringify({state:'BORN_R0_6',world_id:initial.world_id,birth_seed:initial.birth_seed}));
"""
        load = f"vm.runInThisContext(fs.readFileSync({json.dumps(str(JOURNAL))}, 'utf8'), {{filename:'journal.js'}});\nconst journal = GENESIS_WORLD_JOURNAL;\n"
        result = subprocess.run(
            [node, "-e", harness + load + "(async () => {\n" + body + "\n})().catch(error => {console.error(error);process.exit(1);});"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

    def test_roundtrip_preview_cancel_and_explicit_import_keep_birth_and_lighthouse(self):
        self.run_journal(r"""
const originalRaw = store.get(SAVE), originalBirth = store.get(BIRTH);
assert.equal(elements.get('save-status').textContent, 'Сохранено на этом устройстве');
const imported = world({position:12,lighthouse:true});
store.set(SAVE, JSON.stringify(imported));
let flushes = 0; globalThis.GENESIS_WORLD_RUNTIME_V5 = {flushSave:async()=>{flushes++;return true;}};
const portable = await journal.exportText(); assert.equal(flushes,1);
const envelope = JSON.parse(portable); assert.equal(envelope.schema,'janus.genesis.browser_export.v1');
assert.equal(envelope.save.player_position.y,0);
store.set(SAVE, originalRaw);
const preview = await journal.stageImportText(portable);
assert.equal(preview.objects,1); assert.equal(preview.events,5);
assert.equal(store.get(SAVE),originalRaw); assert.equal(store.get(BIRTH),originalBirth); assert.equal(reloads,0);
assert.equal(elements.get('save-import-confirm').hidden,false);
journal.cancelImport(); assert.equal(await journal.confirmImport(),false); assert.equal(store.get(SAVE),originalRaw);
await journal.stageImportText(portable); session.set(PENDING,'old first intent');
let finishPending, fenced=false,resumes=0;
const pendingDrain=new Promise(resolve=>{finishPending=resolve;});
const completeOld=JSON.stringify(world({position:3}));
globalThis.GENESIS_WORLD_RUNTIME_V5={beginWorldReplacement:async()=>{fenced=true;await pendingDrain;store.set(SAVE,completeOld);return()=>{fenced=false;resumes++;};}};
const confirmation=journal.confirmImport();
assert.equal(store.get(SAVE),originalRaw);assert.equal(elements.get('save-import-confirm').disabled,true);
assert.equal(await journal.confirmImport(),false);
finishPending();assert.equal(await confirmation,true); assert.equal(reloads,1);
const after = JSON.parse(store.get(SAVE)); assert.deepEqual(after,imported);
const birth = JSON.parse(store.get(BIRTH)); assert.equal(birth.state,'BORN_R0_6'); assert.equal(birth.birth_seed, imported.birth_seed); assert.equal(birth.event_hash,imported.chronicle_hash_chain[0].event_hash);
assert.equal(session.has(PENDING),false);
const backup = JSON.parse(store.get(BACKUP)); assert.equal(backup.save_text,completeOld); assert.equal(backup.birth_text,originalBirth);
assert.equal(fenced,true);assert.equal(resumes,0);
assert.equal(elements.get('save-import-confirm').hidden,true);
""")

    def test_invalid_files_cannot_stage_or_overwrite_a_world(self):
        self.run_journal(r"""
const original = store.get(SAVE), birth = store.get(BIRTH);
const invalid = [];
invalid.push('{bad json', '{}', 'x'.repeat(2*1024*1024+1));
let changed = world(); changed.world_id='OTHER'; invalid.push(JSON.stringify(changed));
changed=world();changed.player_position.x='0';invalid.push(JSON.stringify(changed));
invalid.push(JSON.stringify(world()).replace('"x":0','"x":1e309'));
changed=world();changed.discovered_chunk_coordinates=Array(8193).fill([0,0]);invalid.push(JSON.stringify(changed));
changed=world();changed.explicit_world_mutations=Array(769).fill({type:'PLAYER_MARK',x:0,y:0});invalid.push(JSON.stringify(changed));
changed=world();changed.chronicle_hash_chain[1].data.chunk=[10,10];invalid.push(JSON.stringify(changed));
changed=world();changed.chronicle_hash_chain[1].prev='0'.repeat(64);invalid.push(JSON.stringify(changed));
changed=world();changed.chronicle_hash_chain[1].sequence=7;invalid.push(JSON.stringify(changed));
changed=world();changed.explicit_world_mutations.push({type:'SPAWNED_ENTITY',entity_kind:'wolf',seed:'123',x:8,y:8});invalid.push(JSON.stringify(changed));
changed=world({lighthouse:true});changed.explicit_world_mutations[0].interaction_state.beacon_lit=false;invalid.push(JSON.stringify(changed));
changed=world({lighthouse:true});changed.explicit_world_mutations[0].mechanics=[{schema:'janus.genesis.mechanic_recipe.v1',kind:'EXEC',params:{},source:'external',remote_code_executed:true}];invalid.push(JSON.stringify(changed));
changed=world();changed.birth_seed='f'.repeat(64);invalid.push(JSON.stringify(changed));
changed=world();changed.chronicle_hash_chain=changed.chronicle_hash_chain.slice(1);invalid.push(JSON.stringify(changed));
invalid.push(JSON.stringify(world()).replace('{"schema"','{"__proto__":{"polluted":true},"schema"'));
invalid.push(JSON.stringify(world()).replace('{"schema"','{"constructor":{"prototype":{}},"schema"'));
changed=world();changed.endpoint='https://example.invalid';invalid.push(JSON.stringify(changed));
const rawExport=await journal.exportText();changed=JSON.parse(rawExport);changed.save.player_position.x=100;invalid.push(JSON.stringify(changed));
for(const raw of invalid) {
  await assert.rejects(journal.stageImportText(raw));
  assert.equal(store.get(SAVE),original);assert.equal(store.get(BIRTH),birth);assert.equal(reloads,0);
  assert.equal(elements.get('save-import-confirm').hidden,true);assert.equal(await journal.confirmImport(),false);
}
assert.equal({}.polluted,undefined);
""")

    def test_storage_failure_rolls_back_and_chronicle_uses_text_nodes(self):
        self.run_journal(r"""
const original = store.get(SAVE), birth = store.get(BIRTH);store.set(BACKUP,'previous backup');
await journal.stageImportText(JSON.stringify(world({position:9,lighthouse:true})));
let fenced=false,resumes=0;
globalThis.GENESIS_WORLD_RUNTIME_V5={beginWorldReplacement:async()=>{fenced=true;return()=>{fenced=false;resumes++;};}};
failSaveOnce=true;
assert.equal(await journal.confirmImport(),false);assert.equal(reloads,0);
assert.equal(store.get(SAVE),original);assert.equal(store.get(BIRTH),birth);assert.equal(store.get(BACKUP),'previous backup');
assert.equal(fenced,false);assert.equal(resumes,1);assert.equal(elements.get('save-import-confirm').disabled,false);
assert.match(elements.get('save-import-status').textContent,/Текущий мир сохранён/);
const list = new Element('ol');const save=world({lighthouse:true});
save.chronicle_hash_chain[2].data.concept='<img src=x onerror=alert(1)>';
journal.renderChronicle(save.chronicle_hash_chain,list);
assert.equal(list.children.length,5);
assert.equal(list.children[0].children[1].children[0].textContent,'Зажжён огонь маяка');
const description=journal.describeEvent(save.chronicle_hash_chain[2]);assert.match(description.description,/<img/);assert.match(description.position,/2.0, 4.0/);
assert.equal(Object.hasOwn(list.children[2].children[1].children[1],'innerHTML'),false);
assert.equal(journal.describeEvent(save.chronicle_hash_chain[0]).time,'');
docEvents.get('genesis:save-error')();assert.match(elements.get('save-status').textContent,/Не удалось сохранить/);
docEvents.get('genesis:save')();assert.equal(elements.get('save-status').textContent,'Сохранено на этом устройстве');
""")

    def test_plain_legacy_save_and_export_never_carry_connection_settings(self):
        self.run_journal(r"""
const save=world({lighthouse:true});
save.explicit_world_mutations[0].asset_refs=[{provider_id:'example',asset_id:'stone',rights:'CC0',name:'Stone',download_pointer:'https://example.invalid/material.glb?token=private',source_url:'https://example.invalid/source?private=secret',license_url:'https://example.invalid/license'}];
save.janus_endpoint='https://private.invalid';save.hosted_bearer_token='not-exported';
store.set(SAVE,JSON.stringify(save));
// World-only whitelisting removes unrelated local settings. A sensitive field in
// supported world data is rejected, rather than accidentally passed through.
await assert.rejects(journal.exportText());
delete save.janus_endpoint;delete save.hosted_bearer_token;store.set(SAVE,JSON.stringify(save));
const exported=await journal.exportText();
assert.doesNotMatch(exported,/download_pointer|token=private|private=secret/);
assert.match(exported,/example.invalid\/source/);
await journal.parseImport(exported);
const legacy=world();delete legacy.birth_state;delete legacy.birth_seed;delete legacy.birth_intent_sha256;
legacy.chronicle_hash_chain=[];legacy.explicit_world_mutations=[{id:'mark-1',type:'PLAYER_MARK',x:1,y:2,recipe:'GENESIS_PLAYER_MARK_R0'}];
const core={sequence:1,previous_hash:'GENESIS_ORIGIN',type:'PLAYER_MARK_PLACED',mutation_id:'mark-1',position:[1,2],chunk:[0,0]};
function stable(value){if(Array.isArray(value))return `[${value.map(stable).join(',')}]`;if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`;return JSON.stringify(value);}
legacy.chronicle_hash_chain=[{...core,event_hash:digest(stable(core))}];
const parsed=await journal.parseImport(JSON.stringify(legacy));
assert.equal(parsed.birth.state,'BORN_LEGACY_R0_5');assert.equal(parsed.birth.retroactive_birth_claim,false);assert.equal(parsed.birth.birth_seed,undefined);
""")


if __name__ == "__main__":
    unittest.main()

