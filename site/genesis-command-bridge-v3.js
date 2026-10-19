(() => {
  'use strict';
  const REQUEST_SCHEMA='janus.genesis.api.request.v1', ENDPOINT_KEY='janus.genesis.api.endpoint.v1', MAX_TEXT=4000;
  const $=id=>document.getElementById(id), runtime=()=>globalThis.GENESIS_WORLD_RUNTIME_V4;
  let endpoint='', online=false, lastHealth=null, requestCounter=0;

  const LEX={
    build:['build','construct','generate','erect','построй','построить','возведи','создай','создать','сделай','поставь','размести','сгенерируй','побудуй','збудуй','створи','зроби','розмісти','zbuduj','stworz','postaw','baue','bauen','erschaffe','construye','crear','crea','construis','cree','creer'],
    spawn:['spawn','summon','add','create','make','place','породи','заспавнь','спавн','призови','добавь','створи','додай','dodaj','spawne','beschwore','fuge','invoca','anade','invoque','ajoute'],
    move:['go','walk','move','travel','explore','wander','forward','backward','иди','идти','двигай','пройди','беги','исследуй','броди','вперед','назад','йди','рухайся','біжи','досліджуй','idz','rusz','biegnij','eksploruj','geh','gehe','lauf','erkunde','camina','muevete','explora','marche','deplace'],
    return:['return','home','hearth','back to fire','вернись','домой','к огню','к костру','повернись','додому','до вогню','wroc','domu','ognia','zuruck','heim','regresa','casa','retourne','maison'],
    mark:['mark','leave mark','sign','метка','метку','оставь знак','поставь метку','познач','залиш знак','znak','markierung','zeichen','marca','senal','marque','signe'],
    inspect:['inspect','scan','describe','what is here','look around','осмотри','что здесь','опиши место','просканируй','оглянь','що тут','опиши місце','sprawdz','opisz','untersuche','beschreibe','inspecciona','describe','inspecte','decris'],
    night:['night','ночь','ніч','noc','nacht','noche','nuit'], day:['day','день','dzien','tag','dia','jour'],
    fog:['fog','mist','туман','імла','mgla','nebel','niebla','brouillard'], clearFog:['clear fog','remove fog','без тумана','убери туман','без туману','прибери туман','usun mgle','nebel aus','quita niebla','retire brouillard'],
    raise:['raise hill','make hill','raise terrain','подними холм','создай холм','подними землю','підніми пагорб','створи пагорб','wzgorze','hugel','colina','colline'],
    lower:['lower ground','dig pit','lower terrain','опусти землю','выкопай яму','зроби яму','grube','senke','hoyo','fosse']
  };
  const DIR={N:['north','север','північ','polnoc','norden','norte','nord'],NE:['northeast','north east','северо-вост','північний схід','nordost','noreste','nord-est'],E:['east','восток','схід','wschod','osten','este','est'],SE:['southeast','south east','юго-вост','південний схід','sudost','sureste','sud-est'],S:['south','юг','південь','poludnie','suden','sur','sud'],SW:['southwest','south west','юго-зап','південний захід','sudwest','suroeste','sud-ouest'],W:['west','запад','захід','zachod','westen','oeste','ouest'],NW:['northwest','north west','северо-зап','північний захід','nordwest','noroeste','nord-ouest'],BACKWARD:['backward','назад','zuruck','atras','arriere']};
  const CAM={FIRST_PERSON:['first person','1st person','первое лицо','от первого лица','від першої особи','pierwsza osoba','ego perspektive','primera persona','premiere personne'],THIRD_PERSON:['third person','3rd person','третье лицо','от третьего лица','від третьої особи','trzecia osoba','dritte person','tercera persona','troisieme personne'],ISOMETRIC:['isometric','isometry','изометр','ізометр','izometr','isometrisch','isometrica','isometrique']};
  const MIR={ORIGIN:['style origin','origin style','стиль origin','стиль исток','стиль початок'],NOCTURNE:['style nocturne','nocturne style','стиль nocturne','стиль ноктюрн'],AETHER:['style aether','aether style','стиль aether','стиль эфир','стиль ефір'],EMBER:['style ember','ember style','стиль ember','стиль жар','стиль попіл']};
  const STRUCTURES={lighthouse:['lighthouse','маяк','latarnia','leuchtturm','faro','phare'],castle:['castle','замок','фортеця','zamek','burg','castillo','chateau'],bridge:['bridge','мост','міст','most','brucke','puente','pont'],tower:['tower','wieza','turm','torre','tour'],house:['house','building','дом','haus','casa','maison'],wall:['wall','стіна','sciana','mauer','muro','mur'],portal:['portal','портал'],tree:['tree','drzewo','baum','arbol','arbre'],statue:['statue','pomnik'],road:['road','droga','strasse','camino','route']};
  const STRUCTURE_STEMS={castle:['крепост','фортец'],tower:['башн','веж'],house:['будин'],wall:['стен'],tree:['дерев'],statue:['стату','памят','пам’ят'],road:['дорог','шлях']};
  const ENTITY_HINTS=['npc','person','human','guard','guardian','creature','animal','dragon','wolf','horse','робот','человек','персонаж','нпс','страж','существо','дракон','волк','кінь','людина','істота','smok','wilk','mensch','drache','persona','personne'];

  function norm(v){return String(v||'').normalize('NFKC').toLowerCase().replace(/ё/g,'е').replace(/[–—−]/g,'-').replace(/\s+/g,' ').trim();}
  function escRx(v){return String(v).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
  function phraseRx(token,global=false){return new RegExp(`(^|[^\\p{L}\\p{N}_])${escRx(token)}(?=$|[^\\p{L}\\p{N}_])`,global?'giu':'iu');}
  function has(text,list){return list.some(v=>phraseRx(v).test(text));}
  function hasFragment(text,list){return list.some(v=>text.includes(v));}
  function mapMatch(text,map){for(const [key,list] of Object.entries(map))if(has(text,list))return key;return null;}
  function hashText(text){let h=0x811c9dc5;for(const ch of String(text)){h^=ch.charCodeAt(0);h=Math.imul(h,0x01000193);}return(h>>>0).toString(16).padStart(8,'0');}
  function numberFrom(text,fallback=1,min=0,max=64){const m=text.match(/(?:^|\s)(-?\d+(?:\.\d+)?)(?:\s|$)/);return Math.max(min,Math.min(max,m?Number(m[1]):fallback));}
  function structureKind(text){for(const [kind,list] of Object.entries(STRUCTURES))if(has(text,list))return kind;for(const [kind,list] of Object.entries(STRUCTURE_STEMS))if(hasFragment(text,list))return kind;return null;}
  function actionSeed(text){return hashText(JSON.stringify(runtime()?.getCanonicalState()||{})+'|'+norm(text));}
  function removePhrase(text,token){return text.replace(phraseRx(token,true),'$1');}
  function concept(text){let s=norm(text);for(const list of Object.values(LEX))for(const token of list)s=removePhrase(s,token);s=s.replace(/\b\d+(?:\.\d+)?\b/g,' ').replace(/[^\p{L}\p{N}_\- ']+/gu,' ').replace(/\s+/g,' ').trim();return s.slice(0,120)||'generated object';}

  function localCompile(raw){
    const text=norm(raw), seed=actionSeed(raw), camera=mapMatch(text,CAM), mirror=mapMatch(text,MIR), direction=mapMatch(text,DIR), sk=structureKind(text);
    if(camera)return{kind:'SET_CAMERA',camera,action_seed:seed};
    if(mirror)return{kind:'SET_MIRROR',mirror,action_seed:seed};
    if(/camera|камера|камер|kamera|camara/.test(text)&&/(distance|дистанц|расстоя|відстан|odleg|entfern|distancia)/.test(text))return{kind:'SET_CAMERA_DISTANCE',distance:numberFrom(text,8,2.5,30),action_seed:seed};
    if(has(text,LEX.return))return{kind:'RETURN_TO_HEARTH',action_seed:seed};
    if(has(text,LEX.mark)&&!has(text,LEX.build))return{kind:'PLACE_MARK',label:raw.slice(0,64),action_seed:seed};
    if(has(text,LEX.inspect))return{kind:'INSPECT',query:raw.slice(0,280),action_seed:seed};
    if(has(text,LEX.clearFog))return{kind:'SET_ATMOSPHERE',fog:0,action_seed:seed};
    if(has(text,LEX.night)||has(text,LEX.day)||has(text,LEX.fog))return{kind:'SET_ATMOSPHERE',time:has(text,LEX.night)?'NIGHT':has(text,LEX.day)?'DAY':undefined,fog:has(text,LEX.fog)?.48:undefined,action_seed:seed};
    if(has(text,LEX.raise))return{kind:'WORLD_TRANSFORM',transform_kind:'RAISE_HILL',radius:numberFrom(text,5,1,16),amount:2.6,action_seed:seed};
    if(has(text,LEX.lower))return{kind:'WORLD_TRANSFORM',transform_kind:'LOWER_GROUND',radius:numberFrom(text,4,1,16),amount:2.0,action_seed:seed};
    if((has(text,LEX.build)||has(text,LEX.spawn))&&sk){const c=concept(text);return{kind:'GENERATE_STRUCTURE',concept:c,structure_kind:sk,action_seed:seed,placement:'IN_FRONT_OF_PLAYER'};}
    if(has(text,LEX.build)){const c=concept(text);return{kind:'GENERATE_STRUCTURE',concept:c,structure_kind:'generic_structure',action_seed:seed,placement:'IN_FRONT_OF_PLAYER'};}
    if(has(text,LEX.spawn)){const c=concept(text);return{kind:'SPAWN_ENTITY',concept:c,entity_kind:has(text,ENTITY_HINTS)?c:'generic_entity',action_seed:seed,placement:'IN_FRONT_OF_PLAYER'};}
    if(has(text,LEX.move)||direction)return{kind:'MOVE',direction:direction||'FORWARD',steps:numberFrom(text,1,1,64),action_seed:seed};
    return{kind:'UNRESOLVED',reason:'LOCAL_DEGRADED_NEEDS_JANUS_SEMANTIC_COMPILER',player_text:raw.slice(0,280),action_seed:seed};
  }

  function apiBase(){return endpoint.replace(/\/+$/,'');}
  function setStatus(ok,text){const s=$('janus-api-status');if(s){s.textContent=text;s.classList.toggle('safe',ok);s.classList.toggle('warn',!ok);}const m=$('world-mode');if(m)m.textContent=ok?'JANUS-ROUTED':'LOCAL DEGRADED';}
  async function healthCheck(){if(!endpoint){online=false;setStatus(false,'NO ENDPOINT');return false;}try{const r=await fetch(apiBase()+'/v1/health',{cache:'no-store',signal:AbortSignal.timeout(2500)});if(!r.ok)throw new Error(`HTTP ${r.status}`);const data=await r.json();online=data?.janus_api_available===true&&data?.genesis_intent_available===true;lastHealth=data;setStatus(online,online?'JANUS HOME ONLINE':'JANUS HEALTH REJECT');return online;}catch(e){online=false;lastHealth=null;setStatus(false,`OFFLINE ${e.name==='TimeoutError'?'TIMEOUT':'NO ROUTE'}`);return false;}}
  function payloadFor(text){return{schema:REQUEST_SCHEMA,request_id:`genesis-${Date.now()}-${++requestCounter}`,player_text:text,language_hint:navigator.language||null,canonical_world_state:runtime().getCanonicalState(),presentation:runtime().getPresentationState(),capabilities:{runtime:'GENESIS_WORLD_RUNTIME_V4',asset_trunk:true,text_native_world_engine:true,cameras:['FIRST_PERSON','THIRD_PERSON','ISOMETRIC'],intent_families:['MOVE','RETURN_TO_HEARTH','PLACE_MARK','GENERATE_STRUCTURE','SPAWN_ENTITY','SET_ATMOSPHERE','WORLD_TRANSFORM','SET_CAMERA','SET_MIRROR','SET_CAMERA_DISTANCE','INSPECT']}};}
  async function janusCompile(text){const r=await fetch(apiBase()+'/v1/genesis/intent',{method:'POST',headers:{'Content-Type':'application/json','X-Janus-Request-Id':`g-${Date.now()}`},body:JSON.stringify(payloadFor(text)),signal:AbortSignal.timeout(7000)});if(!r.ok)throw new Error(`JANUS_API_HTTP_${r.status}`);const data=await r.json();if(data?.schema!=='janus.genesis.api.response.v1'||!data.intent_plan)throw new Error('JANUS_RESPONSE_SCHEMA_INVALID');if(data.authority?.janus_api_is_world_authority!==false||data.authority?.genesis_validator_required!==true)throw new Error('JANUS_AUTHORITY_BOUNDARY_INVALID');return data;}

  async function assetSearch(query,type){if(!online)return[];try{const r=await fetch(apiBase()+`/v1/genesis/assets/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(type)}&limit=5`,{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)return[];const d=await r.json();if(d.provider_id!=='poly_haven'||d.rights_gate!=='PROVIDER_WIDE_CC0_ASSETS')return[];return Array.isArray(d.results)?d.results:[];}catch{return[];}}
  async function assetFiles(assetId){if(!online)return[];try{const r=await fetch(apiBase()+`/v1/genesis/assets/files/${encodeURIComponent(assetId)}`,{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)return[];const d=await r.json();if(d.provider_id!=='poly_haven'||d.rights!=='CC0')return[];return Array.isArray(d.files)?d.files:[];}catch{return[];}}
  function preferredFile(files){const images=files.filter(f=>/\.(?:jpg|jpeg|png|webp)$/i.test(String(f.url||''))),small=images.filter(f=>(Number(f.size)||1e18)<8_000_000);return small[0]||images[0]||null;}
  async function resolveAssets(intent){if(!['GENERATE_STRUCTURE','SPAWN_ENTITY'].includes(String(intent.kind||'').toUpperCase())){renderAssets([]);return[];}if(!online){renderAssets([]);return[];}const q=intent.concept||intent.structure_kind||intent.entity_kind||'stone',rows=await assetSearch(q,'textures'),refs=[];for(const row of rows.slice(0,2)){const file=preferredFile(await assetFiles(row.asset_id));if(file)refs.push({provider_id:'poly_haven',asset_id:row.asset_id,name:row.name,type:row.type,rights:'CC0',source_url:row.source_url,download_pointer:file.url,size:file.size||null});}renderAssets(refs);return refs;}
  function esc(v){return String(v).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
  function renderAssets(refs){const box=$('asset-trunk-results'),count=$('asset-count');if(count)count.textContent=String(refs.length);if(!box)return;box.innerHTML='';if(!refs.length){box.textContent=online?'NO RIGHTS-GATED MATCH / PROCEDURAL KRR FALLBACK':'JANUS OFFLINE / PROCEDURAL KRR FALLBACK';return;}for(const a of refs){const dna=globalThis.GENESIS_ASSET_MATERIALIZER_V2?.materialDNA?.([a],a.asset_id,a.type||'stone');const item=document.createElement('div');item.className='asset-hit';item.innerHTML=`<strong>${esc(a.name||a.asset_id)}</strong><span>${esc(a.type||'asset')} · CC0 · Powered by Poly Haven · KRR ${esc(dna?.hash||'pending')}</span><code>${esc(a.asset_id)}</code>`;box.append(item);}}
  function describe(intent,exec,assets,mode){const kind=String(intent.kind||'').toUpperCase();if(kind==='GENERATE_STRUCTURE')return`MATERIALIZED ${intent.structure_kind||'structure'} · ${exec.mutation?.recipe||'KRR'} · assets ${assets.length} · ${mode}`;if(kind==='SPAWN_ENTITY')return`SPAWNED ${intent.entity_kind||intent.concept||'entity'} · assets ${assets.length} · ${mode}`;if(kind==='INSPECT')return`INSPECT ${JSON.stringify(exec.inspection||{}).slice(0,520)}`;if(kind==='SET_ATMOSPHERE')return`WORLD ATMOSPHERE ${JSON.stringify(exec.world_settings||{})}`;if(kind==='WORLD_TRANSFORM')return`WORLD TRANSFORM ${intent.transform_kind}`;if(kind.startsWith('SET_'))return`PRESENTATION ${kind} APPLIED`;return`EXECUTED ${kind} · ${mode}`;}
  function showFailure(text){const el=$('action-result');if(el)el.textContent=text;}
  function updateStateHash(){const e=$('action-state-hash');if(e)e.textContent=hashText(JSON.stringify(runtime()?.getCanonicalState()||{}));}

  async function executeText(text){
    const raw=String(text||'').trim();if(!raw)return;if(raw.length>MAX_TEXT){showFailure('PLAYER_TEXT_TOO_LONG');return;}const result=$('action-result'),plan=$('action-plan'),button=$('action-submit');if(button)button.disabled=true;if(result)result.textContent='JANUS ROUTING…';
    let response=null,intent=null,mode='LOCAL DEGRADED';
    try{
      if(online){response=await janusCompile(raw);intent=response.intent_plan;mode='JANUS HOME';if(intent?.kind==='UNRESOLVED'){const fallback=localCompile(raw);if(fallback.kind!=='UNRESOLVED'){intent=fallback;mode='JANUS UNRESOLVED → LOCAL BOUNDED FALLBACK';}}}else intent=localCompile(raw);
      if(!intent||intent.kind==='UNRESOLVED'){const reason=intent?.reason||'NO_BOUNDED_MECHANIC';if(plan)plan.textContent=`UNRESOLVED · ${reason}`;showFailure(`${reason}: Genesis did not mutate the world. Connect JANUS HOME for open-ended semantic compilation.`);return;}
      if(plan)plan.textContent=`${mode} → ${intent.kind}${intent.structure_kind?' / '+intent.structure_kind:''}${intent.entity_kind?' / '+intent.entity_kind:''}`;
      const asset_refs=await resolveAssets(intent),exec=runtime().executeIntent(intent,{receipt_hash:response?.receipt_hash||null,asset_refs});if(!exec?.ok)throw new Error(exec?.reason||'GENESIS_VALIDATOR_REJECT');if(result)result.textContent=describe(intent,exec,asset_refs,mode);
    }catch(e){showFailure(`REJECTED / DEGRADED: ${e.message}`);if(online&&/JANUS_API|fetch|ROUTE|Timeout/i.test(e.message)){online=false;setStatus(false,'JANUS ROUTE LOST');}}
    finally{if(button)button.disabled=false;updateStateHash();}
  }

  function configureEndpoint(value){endpoint=String(value||'').trim().replace(/\/+$/,'');if(endpoint)localStorage.setItem(ENDPOINT_KEY,endpoint);else localStorage.removeItem(ENDPOINT_KEY);const input=$('janus-api-endpoint');if(input)input.value=endpoint;healthCheck();}
  function textTarget(target){return target instanceof HTMLInputElement||target instanceof HTMLTextAreaElement||target?.isContentEditable;}
  function focusConsole(select=false){const input=$('action-input');if(!input)return;input.focus({preventScroll:true});if(select&&input.select)input.select();}
  function submitConsole(){const form=$('action-form');if(form?.requestSubmit)form.requestSubmit();else form?.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}
  function setup(){
    const qs=new URLSearchParams(location.search);endpoint=qs.get('janus_api')||localStorage.getItem(ENDPOINT_KEY)||'';const form=$('action-form'),input=$('action-input');
    form?.addEventListener('submit',e=>{e.preventDefault();const text=input?.value||'';executeText(text);if(input){input.value='';input.focus({preventScroll:true});}});
    input?.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Escape'){e.preventDefault();input.blur();return;}if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitConsole();}});input?.addEventListener('keyup',e=>e.stopPropagation());input?.addEventListener('click',e=>e.stopPropagation());
    addEventListener('keydown',e=>{if(document.body?.dataset?.genesisDrawerOpen==='true'||e.target?.closest?.('button,a,summary,select,[role=button]'))return;if(e.key==='Enter'&&!textTarget(e.target)){e.preventDefault();focusConsole(false);}else if(e.key==='Escape'&&document.activeElement===input)input.blur();},true);
    const ep=$('janus-api-endpoint');if(ep){ep.value=endpoint;ep.addEventListener('change',()=>configureEndpoint(ep.value));}$('janus-api-connect')?.addEventListener('click',()=>configureEndpoint(ep?.value||endpoint));updateStateHash();healthCheck();setInterval(healthCheck,15000);setInterval(updateStateHash,1200);
  }
  setup();
  globalThis.GENESIS_COMMAND_BRIDGE_V3=Object.freeze({version:'3.0.1',healthCheck,executeText,configureEndpoint,localCompile,focusConsole,get online(){return online;},get endpoint(){return endpoint;},get health(){return lastHealth;}});
  globalThis.GENESIS_COMMAND_BRIDGE_V2=globalThis.GENESIS_COMMAND_BRIDGE_V3;globalThis.GENESIS_JANUS_BRIDGE=globalThis.GENESIS_COMMAND_BRIDGE_V3;
})();
