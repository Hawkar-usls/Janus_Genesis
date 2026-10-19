(() => {
  'use strict';

  const VERSION='0.6.0';
  const WORLD_ID='GENESIS_ONE_WORLD_R0';
  const WORLD_SEED='genesis-one-world-r0';
  const SAVE_KEY='janus.genesis.world_shell_r0.save.v1';
  const BIRTH_KEY='janus.genesis.birth_r0_6.v1';
  const PENDING_KEY='janus.genesis.birth_r0_6.pending_intent.v1';
  const SENTINEL='UNBORN_BOOT_SENTINEL';
  const CONTRACT_PATH='contracts/GENESIS_BIRTH_R0_6.json';
  let state='BOOTING';

  const parse=value=>{try{return JSON.parse(value||'null');}catch{return null;}};
  const readSave=()=>parse(localStorage.getItem(SAVE_KEY));
  const validWorldSave=save=>Boolean(save&&save.world_id===WORLD_ID&&save.world_seed===WORLD_SEED);
  const eventsOf=save=>Array.isArray(save?.chronicle_hash_chain)?save.chronicle_hash_chain:[];
  const hasEvent=(save,type)=>eventsOf(save).some(event=>event?.type===type);
  const normalizeIntent=value=>String(value||'').trim().replace(/[\s\u00a0]+/gu,' ');

  function sentinelSave(){
    return {
      schema:'janus.genesis.world_shell_save.v1',
      generator_version:'GENESIS_COMMAND_RUNTIME_R0.3.0',
      world_id:WORLD_ID,
      world_seed:WORLD_SEED,
      player_position:{x:.5,y:.5},
      mirror_profile:'ORIGIN',
      camera_mode:'THIRD_PERSON',
      camera_heading:0,
      camera_pitch:-.18,
      camera_roll:0,
      camera_distance:8,
      world_settings:{time:'DAY',fog:.08,weather:'CLEAR'},
      discovered_chunk_coordinates:[[0,0]],
      explicit_world_mutations:[],
      chronicle_hash_chain:[],
      birth_state:SENTINEL,
      birth_sentinel:true,
      birth_version:VERSION
    };
  }

  function isSentinel(save){
    return validWorldSave(save)&&save.birth_state===SENTINEL&&save.birth_sentinel===true&&!eventsOf(save).length;
  }

  function hasLegacyHistory(save){
    if(!validWorldSave(save))return false;
    if(eventsOf(save).length)return true;
    if(Array.isArray(save.explicit_world_mutations)&&save.explicit_world_mutations.length)return true;
    if(Array.isArray(save.discovered_chunk_coordinates)&&save.discovered_chunk_coordinates.length)return true;
    return false;
  }

  function persistBirthRecord(record){
    localStorage.setItem(BIRTH_KEY,JSON.stringify({
      schema:'janus.genesis.birth_state.v1',
      version:VERSION,
      world_id:WORLD_ID,
      ...record
    }));
  }

  function establishBootState(){
    const birth=parse(localStorage.getItem(BIRTH_KEY));
    let save=readSave();

    if(validWorldSave(save)&&hasEvent(save,'GENESIS_BIRTH')){
      if(save.birth_sentinel||save.birth_state===SENTINEL){
        delete save.birth_sentinel;
        save.birth_state='BORN_R0_6';
        localStorage.setItem(SAVE_KEY,JSON.stringify(save));
      }
      state='BORN_R0_6';
      persistBirthRecord({state,birth_seed:save.birth_seed||birth?.birth_seed||null,intent_sha256:save.birth_intent_sha256||birth?.intent_sha256||null});
      return;
    }

    if(birth?.state==='BORN_R0_6'&&validWorldSave(save)){
      state='BORN_R0_6';
      return;
    }

    if(isSentinel(save)){
      state='UNBORN';
      return;
    }

    if(hasLegacyHistory(save)){
      save={...save,birth_state:'BORN_LEGACY_R0_5',birth_version:VERSION};
      delete save.birth_sentinel;
      localStorage.setItem(SAVE_KEY,JSON.stringify(save));
      persistBirthRecord({state:'BORN_LEGACY_R0_5',migration:true,retroactive_birth_claim:false});
      state='BORN_LEGACY_R0_5';
      return;
    }

    // Invalid/empty R0.5 storage would be reset by the old runtime anyway.
    // Seed it with an explicitly non-canonical origin sentinel so R0.5's
    // automatic discover() cannot create CHUNK_DISCOVERED before birth.
    save=sentinelSave();
    localStorage.setItem(SAVE_KEY,JSON.stringify(save));
    persistBirthRecord({state:'UNBORN',boot_sentinel:true});
    state='UNBORN';
  }

  async function sha256(text){
    if(!globalThis.crypto?.subtle)throw new Error('GENESIS_BIRTH_SHA256_UNAVAILABLE');
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
    return [...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');
  }

  function makeVoid(){
    if(document.getElementById('genesis-birth-veil'))return;
    document.documentElement.dataset.genesisBirth='unborn';

    const style=document.createElement('style');
    style.id='genesis-birth-r0-6-style';
    style.textContent=`
      #genesis-birth-veil{position:fixed;inset:0;z-index:2147483000;background:radial-gradient(circle at 50% 42%,#071018 0,#020406 38%,#000 78%);display:grid;place-items:center;padding:24px;color:#e9fbff;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
      #genesis-birth-veil *{box-sizing:border-box}
      .genesis-birth-card{width:min(760px,100%);text-align:center}
      .genesis-birth-eyebrow{display:block;letter-spacing:.24em;font-size:11px;opacity:.56;margin-bottom:18px}
      .genesis-birth-card h1{font:700 clamp(34px,8vw,86px)/.92 system-ui,sans-serif;letter-spacing:-.055em;margin:0 0 18px}
      .genesis-birth-card p{max-width:620px;margin:0 auto 28px;color:#91a7ad;line-height:1.6}
      #genesis-birth-form{display:grid;gap:10px}
      #genesis-birth-intent{width:100%;min-height:92px;resize:vertical;border:1px solid rgba(115,236,255,.28);border-radius:14px;background:rgba(4,12,16,.86);color:#effcff;padding:17px 18px;font:500 16px/1.45 inherit;outline:none;box-shadow:0 18px 70px rgba(0,0,0,.4)}
      #genesis-birth-intent:focus{border-color:#73ecff;box-shadow:0 0 0 3px rgba(115,236,255,.08),0 18px 70px rgba(0,0,0,.45)}
      #genesis-birth-submit{justify-self:center;border:1px solid rgba(115,236,255,.48);border-radius:999px;background:#73ecff;color:#021014;padding:13px 24px;font:800 12px/1 inherit;letter-spacing:.12em;cursor:pointer}
      #genesis-birth-submit:disabled{opacity:.45;cursor:wait}
      #genesis-birth-status{min-height:1.4em;margin-top:8px;font-size:12px;color:#73ecff;letter-spacing:.06em}
      .genesis-birth-law{margin-top:24px;font-size:10px;color:#50636a;letter-spacing:.08em}
    `;
    document.head.appendChild(style);

    const veil=document.createElement('section');
    veil.id='genesis-birth-veil';
    veil.setAttribute('role','dialog');
    veil.setAttribute('aria-modal','true');
    veil.setAttribute('aria-labelledby','genesis-birth-title');
    veil.innerHTML=`<div class="genesis-birth-card"><span class="genesis-birth-eyebrow">GENESIS / R0.6 / BEFORE THE FIRST CAUSE</span><h1 id="genesis-birth-title">НИЧЕГО ЕЩЁ НЕТ.</h1><p>Опиши первое, что должно существовать. Твой текст сначала станет причиной в Chronicle — и только после этого Genesis позволит миру появиться.</p><form id="genesis-birth-form"><textarea id="genesis-birth-intent" maxlength="4000" required aria-label="Первая причина мира" placeholder="Например: пусть в темноте появится один тёплый огонь…"></textarea><button id="genesis-birth-submit" type="submit">ПУСТЬ БУДЕТ</button><div id="genesis-birth-status" aria-live="polite"></div></form><div class="genesis-birth-law">CAUSE → GENESIS_BIRTH → FIRST CHUNK → PLAYER MIRROR</div></div>`;
    document.body.appendChild(veil);

    const form=veil.querySelector('#genesis-birth-form');
    const input=veil.querySelector('#genesis-birth-intent');
    const submit=veil.querySelector('#genesis-birth-submit');
    const status=veil.querySelector('#genesis-birth-status');
    // Let touch players see the first-cause form before opening the keyboard.
    if(!globalThis.matchMedia?.('(any-pointer: coarse)').matches)setTimeout(()=>input?.focus(),30);

    form?.addEventListener('submit',async event=>{
      event.preventDefault();
      if(state!=='UNBORN')return;
      const normalized=normalizeIntent(input?.value);
      if(!normalized){status.textContent='Нужна первая причина.';input?.focus();return;}
      submit.disabled=true;
      status.textContent='JANUS фиксирует первую причину…';
      try{
        await acceptBirth(normalized);
      }catch(error){
        console.error('[GENESIS BIRTH R0.6]',error);
        status.textContent=`BIRTH BLOCKED: ${error?.message||'UNKNOWN'}`;
        submit.disabled=false;
      }
    });
  }

  async function acceptBirth(normalized){
    const save=readSave();
    if(!isSentinel(save))throw new Error('FRESHNESS_CHANGED_RELOAD_REQUIRED');
    if(eventsOf(save).length)throw new Error('PRE_BIRTH_CHRONICLE_NOT_EMPTY');

    const intentSha=await sha256(normalized);
    const birthSeed=await sha256(`GENESIS_BIRTH_R0_6|${WORLD_SEED}|${normalized}`);
    const data={
      birth_version:'R0.6',
      birth_seed:birthSeed,
      intent_sha256:intentSha,
      intent_length:[...normalized].length,
      origin_chunk:[0,0]
    };
    const core={sequence:1,type:'GENESIS_BIRTH',data,prev:'GENESIS'};
    const event_hash=await sha256(JSON.stringify(core));

    const born={
      ...save,
      birth_state:'BORN_R0_6',
      birth_version:VERSION,
      birth_seed:birthSeed,
      birth_intent_sha256:intentSha,
      discovered_chunk_coordinates:[],
      chronicle_hash_chain:[{...core,event_hash}]
    };
    delete born.birth_sentinel;

    // Commit order matters: the non-canonical sentinel disappears in the same
    // local save replacement that introduces the canonical birth event.
    localStorage.setItem(SAVE_KEY,JSON.stringify(born));
    persistBirthRecord({state:'BORN_R0_6',birth_seed:birthSeed,intent_sha256:intentSha,event_hash});
    sessionStorage.setItem(PENDING_KEY,normalized);
    state='BORN_R0_6';
    location.reload();
  }

  function replayPendingIntent(){
    const pending=sessionStorage.getItem(PENDING_KEY);
    if(!pending||state!=='BORN_R0_6')return;
    let attempts=0;
    const poll=()=>{
      attempts+=1;
      const save=readSave();
      const ordered=eventsOf(save);
      const birthIndex=ordered.findIndex(event=>event?.type==='GENESIS_BIRTH');
      const chunkIndex=ordered.findIndex(event=>event?.type==='CHUNK_DISCOVERED');
      const form=document.getElementById('action-form');
      const input=document.getElementById('action-input');
      if(birthIndex===0&&chunkIndex>birthIndex&&form&&input&&typeof form.requestSubmit==='function'){
        sessionStorage.removeItem(PENDING_KEY);
        document.getElementById('enter-world')?.click();
        input.value=pending;
        input.dispatchEvent(new Event('input',{bubbles:true}));
        form.requestSubmit();
        return;
      }
      if(attempts<100){setTimeout(poll,50);return;}
      console.warn('[GENESIS BIRTH R0.6] pending first intent retained; runtime did not expose post-birth discovery in time');
    };
    setTimeout(poll,0);
  }

  establishBootState();
  if(state==='UNBORN')makeVoid();
  else{
    document.documentElement.dataset.genesisBirth=state.toLowerCase();
    window.addEventListener('DOMContentLoaded',replayPendingIntent,{once:true});
  }

  globalThis.GENESIS_BIRTH_R0_6=Object.freeze({
    version:VERSION,
    contract:CONTRACT_PATH,
    getState:()=>state,
    isUnborn:()=>state==='UNBORN',
    normalizeIntent
  });
})();
