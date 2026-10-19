import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GenesisFirstPlayableTests(unittest.TestCase):
    def run_node(self, script):
        node = shutil.which("node")
        self.assertIsNotNone(node)
        result = subprocess.run(
            [node, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_lighthouse_lifecycle_collision_and_persistence(self):
        result = subprocess.run(
            [shutil.which("node"), "tests/genesis_first_playable_harness.js"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GENESIS_FIRST_PLAYABLE_LOOP_PASS", result.stdout)

    def test_real_birth_lighthouse_journal_export_and_import(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),{boot}=require('./tests/genesis_first_playable_harness');
(async()=>{
  const fresh=boot(new Map(),{birth:true});
  await fresh.rt.flushSave();
  assert.equal(fresh.sandbox.GENESIS_BIRTH_R0_6.getState(),'UNBORN');
  fresh.load('site/genesis-world-journal.js');
  const sentinelText=await fresh.sandbox.GENESIS_WORLD_JOURNAL.exportText();
  const sentinel=await fresh.sandbox.GENESIS_WORLD_JOURNAL.parseImport(sentinelText);
  assert.equal(sentinel.birth.state,'UNBORN');
  assert.equal(sentinel.save.chronicle_hash_chain.length,0,'unborn export must not invent discovery or a birth');

  // Use the actual first-cause form handler, including its real SHA-256 birth.
  fresh.elements.get('genesis-birth-intent').value='создай маяк';
  await fresh.listeners.get('genesis-birth-form:submit')({preventDefault(){}});
  assert(fresh.events.some(event=>event.type==='reload'));
  const game=boot(fresh.store,{birth:true,sessionStore:fresh.sessionStore}),rt=game.rt;
  game.load('site/genesis-world-journal.js');
  const journal=game.sandbox.GENESIS_WORLD_JOURNAL;
  const built=rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'lighthouse',concept:'Переносимый маяк',action_seed:'abc12345'});
  assert(built.ok);
  // Export immediately: the journal must wait for queued creation history.
  const darkText=await journal.exportText(),dark=await journal.parseImport(darkText);
  assert.equal(dark.birth.state,'BORN_R0_6');
  assert.equal(dark.save.chronicle_hash_chain[0].type,'GENESIS_BIRTH');
  assert.equal(dark.save.chronicle_hash_chain[1].type,'CHUNK_DISCOVERED');
  assert.equal(dark.save.explicit_world_mutations[0].interaction_state.beacon_lit,false);
  assert.equal(dark.save.explicit_world_mutations[0].interaction_state.door_open,false);

  game.enter();assert(rt.interact({action:'APPROACH'}).ok);
  for(let index=0;index<20;index++)game.tick();
  assert(rt.interact({action:'OPEN_DOOR'}).ok);
  assert(rt.interact({action:'LIGHT_BEACON'}).ok);
  const litText=await journal.exportText(),lit=await journal.parseImport(litText);
  const saved=lit.save.explicit_world_mutations[0];
  assert(saved.interaction_state.door_open&&saved.interaction_state.beacon_lit);
  assert(lit.save.chronicle_hash_chain.some(event=>event.type==='LIGHTHOUSE_DOOR_OPENED'));
  assert(lit.save.chronicle_hash_chain.some(event=>event.type==='BEACON_LIT'));
  const birthHash=lit.save.chronicle_hash_chain[0].event_hash;

  // Move the authentic exported save to another browser store through the real
  // staging/commit API, then boot the real runtime against the imported state.
  const recipient=boot(new Map(),{birth:true});
  await recipient.rt.flushSave();recipient.load('site/genesis-world-journal.js');
  const recipientJournal=recipient.sandbox.GENESIS_WORLD_JOURNAL;
  await recipientJournal.stageImportText(litText);
  assert(await recipientJournal.confirmImport());
  const resumed=boot(recipient.store,{birth:true,sessionStore:recipient.sessionStore});
  await resumed.rt.flushSave();
  assert.equal(resumed.sandbox.GENESIS_BIRTH_R0_6.getState(),'BORN_R0_6');
  assert.equal(resumed.rt.getChronicle()[0].event_hash,birthHash,'import preserves original birth');
  assert.equal(resumed.rt.getChronicle().filter(event=>event.type==='GENESIS_BIRTH').length,1);
  assert.equal(resumed.rt.getNearbyInteractions()[0].id,saved.id);
  assert(resumed.rt.getNearbyInteractions()[0].door_open);
  assert(resumed.rt.getNearbyInteractions()[0].beacon_lit);
  resumed.load('site/genesis-world-journal.js');
  await resumed.sandbox.GENESIS_WORLD_JOURNAL.parseImport(await resumed.sandbox.GENESIS_WORLD_JOURNAL.exportText());
  console.log('REAL_BIRTH_LIGHTHOUSE_JOURNAL_ROUNDTRIP_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
""")

    def test_zero_position_survives_real_journal_roundtrip(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),{boot}=require('./tests/genesis_first_playable_harness');
(async()=>{
  const game=boot(),rt=game.rt;
  rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'lighthouse',concept:'Старый маяк',action_seed:'abc12345'});
  await rt.flushSave();
  const save=JSON.parse(game.store.get('janus.genesis.world_shell_r0.save.v1'));
  // Exercise the valid origin coordinate using an otherwise authentic save.
  save.player_position={x:0,y:0};
  game.store.set('janus.genesis.world_shell_r0.save.v1',JSON.stringify(save));
  const legacy=boot(game.store),old=legacy.rt;
  assert.equal(old.getCanonicalState().player_position.x,0);
  assert.equal(old.getCanonicalState().player_position.y,0);
  assert.equal(old.getNearbyInteractions()[0].beacon_lit,false);
  legacy.load('site/genesis-world-journal.js');
  const journal=legacy.sandbox.GENESIS_WORLD_JOURNAL;
  const text=await journal.exportText(),parsed=await journal.parseImport(text);
  assert.equal(parsed.save.player_position.x,0);
  assert.equal(parsed.save.player_position.y,0);
  assert.equal(parsed.birth.state,'BORN_LEGACY_R0_5');
  // Reimport with a real zero coordinate rather than a truthy fallback to 0.5.
  await journal.stageImportText(text);assert(await journal.confirmImport());
  const loaded=boot(legacy.store);
  assert.equal(loaded.rt.getCanonicalState().player_position.x,0);
  assert.equal(loaded.rt.getCanonicalState().player_position.y,0);
  console.log('ZERO_JOURNAL_ROUNDTRIP_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
""")

    def test_import_waits_for_pending_chronicle_and_fences_old_runtime(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),crypto=require('node:crypto'),{boot}=require('./tests/genesis_first_playable_harness');
(async()=>{
  const SAVE='janus.genesis.world_shell_r0.save.v1',BACKUP='janus.genesis.browser_import.backup.v1';
  const game=boot(),rt=game.rt;
  await rt.flushSave();game.load('site/genesis-world-journal.js');
  const journal=game.sandbox.GENESIS_WORLD_JOURNAL,baseline=await journal.exportText();
  let release,started,holdFirstCreation=true;
  const blocked=new Promise(resolve=>release=resolve),hashStarted=new Promise(resolve=>started=resolve);
  game.sandbox.crypto={subtle:{digest:async(algorithm,data)=>{
    if(holdFirstCreation&&Buffer.from(data).toString('utf8').includes('"type":"STRUCTURE_MATERIALIZED"')){
      holdFirstCreation=false;started();await blocked;
    }
    return crypto.webcrypto.subtle.digest(algorithm,data);
  }}};
  assert(rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'lighthouse',concept:'Pending lighthouse',action_seed:'abc12345'}).ok);
  await hashStarted;
  await journal.stageImportText(baseline);
  let settled=false;
  const commitment=Promise.resolve(journal.confirmImport()).then(value=>{settled=true;return value;});
  await Promise.resolve();await Promise.resolve();
  assert.equal(settled,false,'replacement must wait for the old creation hash');
  assert.equal(game.store.has(BACKUP),false,'backup must wait for a complete old chronicle');
  assert.equal(JSON.parse(game.store.get(SAVE)).explicit_world_mutations.length,1,'import must not replace storage before draining history');
  assert.equal(rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'house',concept:'Late action'}).reason,'WORLD_REPLACED');
  assert.equal(rt.interact({action:'APPROACH'}).reason,'WORLD_REPLACED');
  release();assert.equal(await commitment,true);
  const imported=game.store.get(SAVE);
  assert.equal(JSON.parse(imported).explicit_world_mutations.length,0);
  const backup=JSON.parse(game.store.get(BACKUP));
  const validatedBackup=await journal.parseImport(backup.save_text);
  assert.equal(validatedBackup.save.explicit_world_mutations.length,1);
  assert(validatedBackup.save.chronicle_hash_chain.some(event=>event.type==='STRUCTURE_MATERIALIZED'),'backup must include the completed creation event');
  assert.equal(rt.executeIntent({kind:'PLACE_MARK',label:'Too late'}).reason,'WORLD_REPLACED');
  await rt.flushSave();
  assert.equal(game.store.get(SAVE),imported,'old runtime cannot overwrite the imported world while navigation completes');
  console.log('PENDING_CHRONICLE_IMPORT_FENCE_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
""")

    def test_failed_import_restores_old_world_and_releases_runtime_fence(self):
        self.run_node(r"""
const assert=require('node:assert/strict'),{boot}=require('./tests/genesis_first_playable_harness');
(async()=>{
  const SAVE='janus.genesis.world_shell_r0.save.v1',BACKUP='janus.genesis.browser_import.backup.v1';
  const game=boot(),rt=game.rt;
  await rt.flushSave();game.load('site/genesis-world-journal.js');
  const journal=game.sandbox.GENESIS_WORLD_JOURNAL,baseline=await journal.exportText();
  assert(rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'lighthouse',concept:'Keep this lighthouse',action_seed:'abc12345'}).ok);
  await journal.stageImportText(baseline);
  const originalSet=game.sandbox.localStorage.setItem;
  let failSaveAfterBackup=false;
  game.sandbox.localStorage.setItem=(key,value)=>{
    if(key===SAVE&&failSaveAfterBackup){failSaveAfterBackup=false;throw new Error('Simulated import storage failure');}
    originalSet(key,value);
    if(key===BACKUP)failSaveAfterBackup=true;
  };
  assert.equal(await journal.confirmImport(),false);
  game.sandbox.localStorage.setItem=originalSet;
  assert.equal(JSON.parse(game.store.get(SAVE)).explicit_world_mutations.length,1,'failed replacement restores the complete original world');
  assert.equal(game.store.has(BACKUP),false,'rollback restores the previous backup slot');
  assert.equal(game.events.some(event=>event.type==='reload'),false);
  assert(rt.executeIntent({kind:'PLACE_MARK',label:'After rollback'}).ok,'failed replacement releases the mutation latch');
  assert.equal(await rt.flushSave(),true,'failed replacement resumes persistence');
  const valid=await journal.parseImport(await journal.exportText());
  assert.equal(valid.save.explicit_world_mutations.length,2);
  assert(valid.save.chronicle_hash_chain.some(event=>event.type==='PLAYER_MARK'));
  console.log('FAILED_IMPORT_RESTORES_AND_RESUMES_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
""")


if __name__ == "__main__":
    unittest.main()
