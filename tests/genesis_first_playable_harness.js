'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const path=require('node:path'),root=path.resolve(__dirname,'..');
function boot(store=new Map(),options={}){
  let now=1000,frame;
  const events=[],listeners=new Map(),elements=new Map(),noop=()=>{};
  const context2d=new Proxy({}, {get:(target,key)=>key==='createLinearGradient'?()=>({addColorStop:noop}):key==='createPattern'?()=>null:target[key]??noop,set:(target,key,value)=>(target[key]=value,true)});
  function makeElement(id){return{id,hidden:false,textContent:'',innerHTML:'',classList:{toggle:noop,add:noop,remove:noop},style:{},dataset:{},getContext:()=>context2d,addEventListener:(type,fn)=>listeners.set(id+':'+type,fn),setPointerCapture:noop,focus:noop,append:noop,appendChild:child=>elements.set(child.id,child),replaceChildren:noop,setAttribute:noop,remove:noop,querySelector:selector=>element(selector.replace(/^#/,'')),width:180,height:180};}
  function element(id){if(!elements.has(id))elements.set(id,makeElement(id));return elements.get(id);}
  const sandbox={console,TextEncoder,crypto:crypto.webcrypto,innerWidth:800,innerHeight:600,devicePixelRatio:1,navigator:{hardwareConcurrency:2,deviceMemory:2,language:'ru'},performance:{now:()=>now},requestAnimationFrame:fn=>{frame=fn;},addEventListener:noop,HTMLInputElement:class{},HTMLTextAreaElement:class{},CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},localStorage:{getItem:key=>store.get(key)||null,setItem:(key,value)=>store.set(key,String(value)),removeItem:key=>store.delete(key)}};
  sandbox.window=sandbox;sandbox.location={reload:()=>events.push({type:'reload'})};sandbox.URL=URL;sandbox.setTimeout=noop;
  const sessionStore=options.sessionStore||new Map();sandbox.sessionStorage={getItem:key=>sessionStore.get(key)||null,setItem:(key,value)=>sessionStore.set(key,String(value)),removeItem:key=>sessionStore.delete(key)};
  sandbox.document={readyState:'loading',head:{appendChild:child=>elements.set(child.id,child)},body:{dataset:{},appendChild:child=>elements.set(child.id,child)},documentElement:{dataset:{},style:{setProperty:noop}},activeElement:null,getElementById:id=>id==='genesis-birth-veil'&&!elements.has(id)?null:element(id),querySelectorAll:()=>[],createElement:()=>makeElement('created'),addEventListener:noop,dispatchEvent:event=>events.push(event)};
  vm.createContext(sandbox);
  for(const file of [...(options.birth?['site/genesis-birth-r0-6.js']:[]),'site/genesis-mechanic-forge-r0-5.js','site/genesis-world-runtime-v5.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),sandbox,{filename:file});
  return{rt:sandbox.GENESIS_WORLD_RUNTIME_V5,sandbox,store,events,listeners,elements,sessionStore,load:file=>vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),sandbox,{filename:file}),enter:()=>listeners.get('enter-world:click')(),tick:(ms=50)=>{now+=ms;frame(now);}};
}
async function run(){
  const game=boot(),rt=game.rt;
  await rt.flushSave();
  const original=JSON.stringify(rt.getCanonicalState());
  assert.equal(rt.interact({action:'LIGHT_BEACON'}).reason,'LIGHTHOUSE_NOT_FOUND');
  assert.equal(JSON.stringify(rt.getCanonicalState()),original,'failed action does not mutate');
  assert(rt.executeIntent({kind:'INSPECT'}).inspection.nearby.some(item=>item.type==='FIRST_FIRE'),'inspection sees actual first fire');
  const built=rt.executeIntent({kind:'GENERATE_STRUCTURE',structure_kind:'lighthouse',concept:'Test lighthouse',action_seed:'abc12345'});
  assert(built.ok);assert.equal(built.mutation.interaction_state.beacon_lit,false);
  assert.equal(rt.interact({action:'OPEN_DOOR'}).reason,'TOO_FAR');
  assert.equal(rt.interact({action:'LIGHT_BEACON'}).reason,'TOO_FAR');
  game.enter();assert(rt.interact({action:'APPROACH'}).ok);
  for(let i=0;i<30;i++)game.tick();
  assert(rt.getNearbyInteractions()[0].distance<2.5,'approach walks into reach');
  assert.equal(rt.interact({action:'LIGHT_BEACON'}).reason,'DOOR_CLOSED');
  const hitWall=rt.executeIntent({kind:'MOVE',direction:'FORWARD',steps:10});
  assert(hitWall.blocked,'closed lighthouse wall stops text movement');
  const atWall=rt.getCanonicalState().player_position;
  assert(atWall.y<built.mutation.y-.6,'player cannot tunnel through closed wall');
  const id=rt.getNearbyInteractions()[0].id;
  assert.equal(rt.interact({action:'OPEN_DOOR',target_id:'missing'}).reason,'TARGET_NOT_FOUND');
  assert(rt.interact({action:'OPEN_DOOR',target_id:id}).ok);
  assert.equal(rt.interact({action:'OPEN_DOOR'}).reason,'ALREADY_OPEN');
  assert(rt.interact({action:'LIGHT_BEACON'}).ok);
  assert.equal(rt.getNearbyInteractions()[0].beacon_lit,true);
  assert.equal(rt.interact({action:'LIGHT_BEACON'}).reason,'ALREADY_LIT');
  const throughDoor=rt.executeIntent({kind:'MOVE',direction:'FORWARD',steps:1});
  assert(throughDoor.ok&&throughDoor.moved>.7,'open door permits entry');
  assert(rt.interact({action:'EXTINGUISH_BEACON'}).ok);
  assert(rt.interact({action:'LIGHT_BEACON'}).ok);
  await rt.flushSave();
  const rows=rt.getChronicle();
  for(let i=0;i<rows.length;i++){
    const row=rows[i],core={sequence:row.sequence,type:row.type,data:row.data,prev:row.prev};
    assert.equal(row.sequence,i+1,'concurrent chronicle writes remain ordered');
    assert.equal(row.prev,i?rows[i-1].event_hash:'GENESIS');
    assert.equal(row.event_hash,crypto.createHash('sha256').update(JSON.stringify(core)).digest('hex'));
  }
  assert(rows.some(row=>row.type==='LIGHTHOUSE_DOOR_OPENED'));
  assert(rows.some(row=>row.type==='BEACON_LIT'));
  const restored=boot(game.store);await restored.rt.flushSave();
  assert.equal(restored.rt.getNearbyInteractions()[0].id,id);
  assert.equal(restored.rt.getNearbyInteractions()[0].door_open,true);
  assert.equal(restored.rt.getNearbyInteractions()[0].beacon_lit,true,'beacon survives reload');
  const detached=rt.getCanonicalState();detached.explicit_world_mutations[0].interaction_state.beacon_lit=false;
  assert.equal(rt.getNearbyInteractions()[0].beacon_lit,true,'state snapshots cannot change canonical world');
  const exported=JSON.parse(game.store.get('janus.genesis.world_shell_r0.save.v1'));
  exported.player_position={x:0,y:0};game.store.set('janus.genesis.world_shell_r0.save.v1',JSON.stringify(exported));
  const zero=boot(game.store);assert.equal(zero.rt.getCanonicalState().player_position.x,0,'zero position survives load');
  game.sandbox.document.body.dataset.genesisDrawerOpen='true';
  const before=JSON.stringify(rt.getCanonicalState().player_position);game.tick();
  assert.equal(JSON.stringify(rt.getCanonicalState().player_position),before,'dialog pauses approach');
  console.log('GENESIS_FIRST_PLAYABLE_LOOP_PASS',rows.length,'validated events');
}
module.exports={boot};
if(require.main===module)run().catch(error=>{console.error(error);process.exitCode=1;});
