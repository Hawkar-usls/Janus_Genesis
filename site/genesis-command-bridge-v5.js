(() => {
  'use strict';
  const REQUEST_SCHEMA='janus.genesis.api.request.v1',GRAPH_SCHEMA='janus.genesis.scene_graph.v1',GRAPH_VERSION='0.4.0',LIMITS=Object.freeze({max_nodes:32,max_edges:64,max_depth:8,max_resource_units:128,max_node_resource_units:16}),$=id=>document.getElementById(id),bridge3=()=>globalThis.GENESIS_COMMAND_BRIDGE_V3,executor=()=>globalThis.GENESIS_SCENE_GRAPH_EXECUTOR_R0_5,runtime=()=>globalThis.GENESIS_WORLD_RUNTIME_V5;let requestCounter=0,inFlight=false;
  function norm(v){return String(v||'').normalize('NFKC').toLowerCase().replace(/ё/g,'е').replace(/\s+/g,' ').trim();}
  function shortHash(value){let h1=0x811c9dc5,h2=0x9e3779b9;for(const ch of String(value)){const c=ch.charCodeAt(0);h1^=c;h1=Math.imul(h1,0x01000193);h2^=(c+h1);h2=Math.imul(h2,0x85ebca6b);}return((h1>>>0).toString(16).padStart(8,'0')+(h2>>>0).toString(16).padStart(8,'0')).slice(0,16);}
  function nodeId(seed,ordinal,family,operation,concept){return`n-${shortHash(`${seed}|${ordinal}|${family}|${operation}|${concept}`)}`;}
  function makeNode(seed,nodes,family,operation,concept,params={},deps=[],required=true,resource_units=1){const node={id:nodeId(seed,nodes.length,family,operation,concept),family,operation,concept:String(concept).slice(0,160),params:{...params},depends_on:[...deps],required,resource_units};nodes.push(node);return node;}
  function baseGraph(seed,text,nodes){const graph={schema:GRAPH_SCHEMA,version:GRAPH_VERSION,graph_id:`sg-local-${shortHash(seed+'|'+text)}`,request_id:`local-${Date.now()}-${++requestCounter}`,normalized_text:norm(text),action_seed:seed,world_state_hash:shortHash(JSON.stringify(runtime()?.getCanonicalState()||{})),nodes,limits:{...LIMITS},execution_policy:{order:'TOPOLOGICAL',validate_whole_graph_before_first_mutation:true,partial_failure:'DEPENDENTS_SKIP_FAILED_REQUIRED_ANCESTOR',successful_prior_nodes_are_not_silently_rolled_back:true,node_receipt_required:true,silent_noop_forbidden:true},authority:{janus_graph_is_world_authority:false,model_output_is_command:false,genesis_validator_required:true,world_mutation_authorized_by_janus:false,external_effect_authorized:false},provenance:{compiler:'GENESIS_LOCAL_DEGRADED_SCENE_GRAPH_R0_5',authority:'LOCAL_BOUNDED_NOT_JANUS'}};const check=executor().validateGraph(graph);graph.topological_order=check.order;return graph;}
  const has=(text,...parts)=>parts.some(p=>text.includes(p));
  function interactionIntent(raw){
    let text=norm(raw).replace(/[.!?]+$/,'').replace(/^(?:пожалуйста[, ]+|please )/,'');
    const target=text.match(/\s+(?:#|id[:=]\s*)([a-z0-9:_-]{1,120})$/i);
    if(target)text=text.slice(0,target.index).trim();
    const patterns=[
      ['APPROACH',/^(?:(?:подойди|подойти|иди|идти)\s+к\s+маяку|(?:approach|go to|walk to)\s+(?:the\s+)?(?:lighthouse|beacon))$/],
      ['OPEN_DOOR',/^(?:(?:открой|открыть)\s+дверь(?:\s+маяка)?|open\s+(?:the\s+)?(?:(?:lighthouse|beacon)\s+)?door)$/],
      ['LIGHT_BEACON',/^(?:(?:зажги|зажечь|включи)\s+(?:маяк|огонь(?:\s+маяка)?)|(?:light|ignite|turn on)\s+(?:the\s+)?(?:lighthouse|beacon))$/],
      ['EXTINGUISH_BEACON',/^(?:(?:погаси|погасить|выключи)\s+(?:маяк|огонь(?:\s+маяка)?)|(?:extinguish|turn off)\s+(?:the\s+)?(?:lighthouse|beacon))$/]
    ];
    const match=patterns.find(([,pattern])=>pattern.test(text));
    return match?{kind:'INTERACT',action:match[0],...(target?{target_id:target[1]}:{})}:null;
  }
  function localGraph(raw){const b3=bridge3(),single=interactionIntent(raw)||b3?.localCompile?.(raw)||{kind:'UNRESOLVED',reason:'LOCAL_COMPILER_UNAVAILABLE'},text=norm(raw),seed=String(single.action_seed||shortHash(raw)),nodes=[],cathedral=has(text,'собор','кафедраль','cathedral','церкв','church');if(cathedral){let hill=null,weathered=null;if(has(text,'на холме','на пагорбі','on a hill','on the hill'))hill=makeNode(seed,nodes,'TERRAIN','WORLD_TRANSFORM','scene hill',{transform_kind:'RAISE_HILL',radius:7,amount:2.8,distance:5},[],true,3);if(has(text,'заброш','покинут','занедбан','abandoned','weathered','ruined'))weathered=makeNode(seed,nodes,'MATERIAL','RESOLVE_MATERIAL','weathered stone',{query:'weathered old stone',rights_required:'CC0',fallback:'KRR_WEATHERED_STONE_R1'},[],false,2);const root=makeNode(seed,nodes,'STRUCTURE','GENERATE_STRUCTURE',weathered?'abandoned cathedral':'cathedral',{structure_kind:'generic_structure',placement:'IN_FRONT_OF_PLAYER',distance:5,style:'CATHEDRAL_R0',action_seed:seed},[hill,weathered].filter(Boolean).map(n=>n.id),true,8);if(has(text,'башня разруш','башни разруш','разрушенная башн','зруйнована веж','tower ruined','ruined tower'))makeNode(seed,nodes,'EFFECT','RUINED_TOWER','ruined tower',{target:root.id,visual_fallback:'GENERATE_RUINED_TOWER'},[root.id],false,3);let organ=null;if(has(text,'внутри орган','всередині орган','inside organ','organ inside','pipe organ')){organ=makeNode(seed,nodes,'ENTITY','SPAWN_ENTITY','pipe organ',{entity_kind:'architectural_prop',concept:'pipe organ',placement:'INSIDE_PARENT',target:root.id,action_seed:seed},[root.id],true,4);makeNode(seed,nodes,'SOUND','AUDIO_CUE','cathedral organ ambience',{cue:'resolve',profile:'ORGAN_DRONE_R0'},[organ.id],false,2);}let grove=null;if(has(text,'белые дерев','білі дерев','white trees','white tree'))grove=makeNode(seed,nodes,'ENTITY','SPAWN_GROUP','white trees',{entity_kind:'tree_grove',concept:'white trees',count:5,appearance:'WHITE_BARK',placement:'AT_ENTRANCE',target:root.id,action_seed:seed},[root.id],true,6);if(has(text,'у входа','біля входу','at the entrance','near the entrance'))makeNode(seed,nodes,'RULE','SPATIAL_RELATION','entrance placement relation',{relation:'AT_ENTRANCE',target:root.id,subject:grove?.id||null},[root.id,...(grove?[grove.id]:[])],false,1);return baseGraph(seed,raw,nodes);}if(single.kind==='UNRESOLVED'){makeNode(seed,nodes,'INSPECTION','VISIBLE_FAILURE','unresolved player command',{reason:single.reason||'LOCAL_DEGRADED_NEEDS_JANUS_SEMANTIC_COMPILER'},[],false,0);return baseGraph(seed,raw,nodes);}const map={GENERATE_STRUCTURE:'STRUCTURE',SPAWN_ENTITY:'ENTITY',SET_ATMOSPHERE:'ATMOSPHERE',WORLD_TRANSFORM:'TERRAIN',SET_CAMERA:'PRESENTATION',SET_MIRROR:'PRESENTATION',SET_CAMERA_DISTANCE:'PRESENTATION',INSPECT:'INSPECTION',MOVE:'NAVIGATION',JUMP:'NAVIGATION',RETURN_TO_HEARTH:'NAVIGATION',PLACE_MARK:'NAVIGATION',INTERACT:'NAVIGATION'},family=map[single.kind];if(!family){makeNode(seed,nodes,'INSPECTION','VISIBLE_FAILURE','unsupported local intent',{reason:'LOCAL_GRAPH_FAMILY_UNSUPPORTED'},[],false,0);return baseGraph(seed,raw,nodes);}const params={...single};delete params.kind;delete params.action_seed;if(single.action_seed)params.action_seed=single.action_seed;makeNode(seed,nodes,family,single.kind,single.concept||single.query||single.label||single.kind,params,[],true,['STRUCTURE','ENTITY'].includes(family)?3:1);return baseGraph(seed,raw,nodes);}
  function payloadFor(text){const rt=runtime();return{schema:REQUEST_SCHEMA,request_id:`genesis-scene-${Date.now()}-${++requestCounter}`,player_text:text,language_hint:navigator.language||null,canonical_world_state:rt.getCanonicalState(),presentation:rt.getPresentationState(),capabilities:{runtime:'GENESIS_WORLD_RUNTIME_V5',scene_graph:'0.5-client/0.4-wire',asset_trunk_channels:['material','mesh','audio','mechanic'],jump:true,audio_graph_nodes:true,effect_graph_nodes:true,text_native_world_engine:true}};}
  function endpoint(){return String(bridge3()?.endpoint||'').replace(/\/+$/,'');}
  async function remoteGraph(text){const ep=endpoint();if(!ep)throw new Error('JANUS_SCENE_ENDPOINT_REQUIRED');const r=await fetch(ep+'/v1/genesis/scene-graph',{method:'POST',headers:{'Content-Type':'application/json','X-Janus-Request-Id':`sg-${Date.now()}`},body:JSON.stringify(payloadFor(text)),signal:AbortSignal.timeout(9000)});if(!r.ok)throw new Error(`JANUS_SCENE_GRAPH_HTTP_${r.status}`);const data=await r.json();await executor().verifyTransport(data);return data;}
  async function legacyMaterial(query){const ep=endpoint();if(!bridge3()?.online||!ep)return{ok:true,mode:'PROCEDURAL_KRR_FALLBACK',asset_refs:[]};try{const sr=await fetch(ep+`/v1/genesis/assets/search?q=${encodeURIComponent(query||'stone')}&type=textures&limit=2`,{cache:'no-store',signal:AbortSignal.timeout(7000)});if(!sr.ok)return{ok:true,mode:'PROCEDURAL_KRR_FALLBACK',asset_refs:[]};const search=await sr.json();if(search.provider_id!=='poly_haven'||search.rights_gate!=='PROVIDER_WIDE_CC0_ASSETS')return{ok:true,mode:'PROCEDURAL_KRR_FALLBACK',asset_refs:[]};const refs=[];for(const row of(search.results||[]).slice(0,2)){const fr=await fetch(ep+`/v1/genesis/assets/files/${encodeURIComponent(row.asset_id)}`,{cache:'no-store',signal:AbortSignal.timeout(7000)});if(!fr.ok)continue;const files=await fr.json(),file=(files.files||[]).filter(f=>/\.(?:jpg|jpeg|png|webp)$/i.test(String(f.url||''))).sort((a,b)=>(Number(a.size)||1e18)-(Number(b.size)||1e18))[0];if(files.provider_id==='poly_haven'&&files.rights==='CC0'&&file)refs.push({provider_id:'poly_haven',asset_id:row.asset_id,name:row.name,type:'material',rights:'CC0',source_url:row.source_url,download_pointer:file.url,size:file.size||null,binary_transport:'DIRECT_PROVIDER_CDN_NOT_SLIME'});}return{ok:true,mode:refs.length?'LEGACY_POLY_HAVEN_REFERENCE':'PROCEDURAL_KRR_FALLBACK',asset_refs:refs};}catch{return{ok:true,mode:'PROCEDURAL_KRR_FALLBACK',asset_refs:[]};}}
  async function resolveAsset(kind,query,policy={}){const trunk=globalThis.GENESIS_ASSET_TRUNK_R0_5;if(trunk){const out=await trunk.search(kind,query,{limit:policy.limit||4});if(out.refs?.length||kind!=='material')return{ok:out.ok,mode:out.mode,asset_refs:out.refs||[],providers:out.providers||[]};}if(kind==='material')return legacyMaterial(query);return{ok:true,mode:'PROCEDURAL_OR_LOCAL_RECIPE_FALLBACK',asset_refs:[]};}
  function renderAssets(receipt){
    const box=$('asset-trunk-results'),count=$('asset-count'),refs=(receipt.node_receipts||[]).flatMap(row=>row.asset_refs||[]);
    if(count)count.textContent=String(refs.length);
    if(!box)return;
    box.textContent='';
    if(!refs.length){box.textContent='Использованы локальные материалы и рецепты.';return;}
    for(const asset of refs.slice(0,12)){
      const item=document.createElement('div');item.className='asset-hit';
      const name=document.createElement('strong');name.textContent=String(asset.name||asset.asset_id||'Материал');
      const meta=document.createElement('span');meta.textContent=`${asset.type||'asset'} · ${asset.rights||'RIGHTS?'} · ${asset.provider_id||''}`;
      const code=document.createElement('code');code.textContent=String(asset.asset_id||'');
      item.append(name,meta,code);box.append(item);
    }
  }
  function fallbackDescription(receipt){
    const rows=receipt.node_receipts||[],applied=rows.filter(row=>row.status==='APPLIED').length;
    return{title:applied?'Действие выполнено':'Действие не выполнено',paragraphs:[`Выполнено действий: ${applied} из ${rows.length}. Подробности — в техническом отчёте.`],suggestions:[],status:applied===rows.length?'applied':'partial'};
  }
  function technicalReport(value,label='Технический отчёт'){
    const details=document.createElement('details');details.className='command-technical-report';
    const summary=document.createElement('summary');summary.textContent=label;
    const pre=document.createElement('pre');pre.textContent=JSON.stringify(value,null,2);
    details.append(summary,pre);return details;
  }
  function renderDescription(description,technical){
    const result=$('action-result');if(!result)return;
    result.textContent='';result.setAttribute?.('role','status');result.setAttribute?.('aria-live','polite');result.setAttribute?.('aria-busy','false');
    const head=document.createElement('strong');head.className='player-feedback-title';head.textContent=description.title;result.append(head);
    for(const text of description.paragraphs||[]){const paragraph=document.createElement('p');paragraph.textContent=text;result.append(paragraph);}
    if(description.suggestions?.length){
      const actions=document.createElement('div');actions.className='command-suggestions';actions.setAttribute?.('aria-label','Что можно сделать дальше');
      for(const suggestion of description.suggestions){
        const button=document.createElement('button');button.type='button';button.className='command-suggestion';button.textContent=suggestion.label;
        button.addEventListener('click',()=>executeText(suggestion.text));actions.append(button);
      }
      result.append(actions);
    }
    if(technical)result.append(technicalReport(technical));
  }
  function renderReceipt(receipt,mode,context={}){
    const plan=$('action-plan'),count=receipt.counts?.nodes??receipt.node_receipts?.length??0;
    if(plan)plan.textContent=`${mode} → SCENE GRAPH ${receipt.graph_id} · ${count} nodes`;
    const description=globalThis.GENESIS_PLAYER_FEEDBACK?.describeReceipt(receipt,context)||fallbackDescription(receipt);
    renderDescription(description,receipt);renderAssets(receipt);return description;
  }
  function show(text){const result=$('action-result');if(result){result.textContent=text;result.setAttribute?.('role','status');result.setAttribute?.('aria-live','polite');}}
  async function executeText(text){
    const raw=String(text||'').trim();if(!raw)return null;
    if(inFlight)return{ok:false,error:'COMMAND_BUSY'};
    if(raw.length>4000){
      const description=globalThis.GENESIS_PLAYER_FEEDBACK?.describeFailure('PLAYER_TEXT_TOO_LONG');
      if(description)renderDescription(description,{error:'PLAYER_TEXT_TOO_LONG'});else show('Сократи команду до 4000 символов.');
      return{ok:false,error:'PLAYER_TEXT_TOO_LONG'};
    }
    const button=$('action-submit'),result=$('action-result');inFlight=true;
    if(button)button.disabled=true;
    show('Разбираю команду…');result?.setAttribute?.('aria-busy','true');
    let mode='LOCAL DEGRADED GRAPH';
    try{
      const before=JSON.parse(JSON.stringify(runtime()?.getCanonicalState()||{}));
      let graph,response=null;
      if(!interactionIntent(raw)&&bridge3()?.online&&bridge3()?.health?.scene_graph_available===true){
        try{response=await remoteGraph(raw);graph=response.scene_graph;mode='JANUS HOME SCENE GRAPH';}
        catch(error){graph=localGraph(raw);mode=`JANUS GRAPH LOST → LOCAL DEGRADED (${error.message})`;}
      }else graph=localGraph(raw);
      executor().validateGraph(graph);show('Выполняю действие…');
      const receipt=await executor().executeGraph(graph,{janus_receipt_hash:response?.receipt_hash||null,resolveAsset,source:mode});
      const context={graph,before,after:runtime()?.getCanonicalState(),presentation:runtime()?.getPresentationState(),mode};
      const description=renderReceipt(receipt,mode,context);
      const approach=graph.nodes.find(node=>node.operation==='INTERACT'&&node.params?.action==='APPROACH');
      if(approach&&receipt.node_receipts.some(row=>row.node_id===approach.id&&row.status==='APPLIED')&&document.body?.dataset?.genesisDrawerOpen!=='true'){
        // Text entry pauses locomotion; a confirmed walking command hands
        // control back to the world so desktop typing cannot stall the walk.
        if(document.activeElement===$('action-input'))$('action-input')?.blur();
        $('genesis-world')?.focus?.({preventScroll:true});
      }
      if(typeof globalThis.CustomEvent==='function'&&typeof globalThis.dispatchEvent==='function')globalThis.dispatchEvent(new CustomEvent('genesis:command-complete',{detail:{receipt,graph,description}}));
      return receipt;
    }catch(error){
      const code=error?.message||String(error),description=globalThis.GENESIS_PLAYER_FEEDBACK?.describeFailure(code);
      if(description)renderDescription(description,{error:code,source:mode});else show('Не удалось выполнить действие. Попробуй осмотреть место.');
      return{ok:false,error:code};
    }finally{
      inFlight=false;if(button)button.disabled=false;result?.setAttribute?.('aria-busy','false');
    }
  }
  function setup(){const form=$('action-form'),input=$('action-input');if(!form)return;form.addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation();const text=input?.value||'';if(input){input.value='';if(globalThis.matchMedia?.('(any-pointer: coarse)').matches)input.blur();else input.focus({preventScroll:true});}executeText(text);},true);}
  setup();const api=Object.freeze({version:'5.0.0',executeText,localGraph,remoteGraph,resolveAsset});globalThis.GENESIS_COMMAND_BRIDGE_V5=api;globalThis.GENESIS_COMMAND_BRIDGE_V4=api;globalThis.GENESIS_JANUS_BRIDGE=api;
})();
