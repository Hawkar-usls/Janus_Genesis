"""Player-facing receipt descriptions and the command bridge's DOM boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK = ROOT / "site" / "genesis-player-feedback.js"
BRIDGE = ROOT / "site" / "genesis-command-bridge-v5.js"


class GenesisPlayerFeedbackTests(unittest.TestCase):
    def run_node(self, script, *, bridge=False, feedback=True):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for browser-module tests")
        bootstrap = "const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');\n"
        if bridge:
            bootstrap += r"""
class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.attributes={};this._text='';this.open=false; }
  set textContent(value) { this._text=String(value);this.children=[]; }
  get textContent() { return this._text+this.children.map(child=>child.textContent).join(' '); }
  set innerHTML(value) { throw new Error('Untrusted HTML rendering is forbidden'); }
  append(...children) { this.children.push(...children); }
  setAttribute(name,value) { this.attributes[name]=value; }
  addEventListener() {}
}
const elements=new Map(['action-result','action-plan','action-submit','asset-count','asset-trunk-results'].map(id=>[id,new Element('div')]));
globalThis.document={getElementById:id=>elements.get(id)||null,createElement:tag=>new Element(tag)};
const world={player_position:{x:0.5,y:0.5}};
globalThis.GENESIS_WORLD_RUNTIME_V5={getCanonicalState:()=>world,getPresentationState:()=>({})};
globalThis.GENESIS_COMMAND_BRIDGE_V3={online:false,localCompile:()=>({kind:'INSPECT'})};
globalThis.GENESIS_SCENE_GRAPH_EXECUTOR_R0_5={
  validateGraph:graph=>({order:graph.nodes.map(node=>node.id)}),
  executeGraph:async graph=>({
    graph_id:graph.graph_id,
    node_receipts:graph.nodes.map(node=>({
      node_id:node.id,operation:node.operation,status:'APPLIED',
      result:node.operation==='INSPECT'
        ?{inspection:{biome:'meadow',position:{x:0.5,y:0.5},nearby:[{kind:'lighthouse',concept:'<img src=x onerror=alert(1)>',distance:4}]}}
        :{interaction:{name:'маяк',action:node.params.action,distance:4}}
    }))
  })
};
"""
        if feedback:
            bootstrap += f"vm.runInThisContext(fs.readFileSync({json.dumps(str(FEEDBACK))},'utf8'));\n"
        if bridge:
            bootstrap += f"vm.runInThisContext(fs.readFileSync({json.dumps(str(BRIDGE))},'utf8'));\n"
        completed = subprocess.run(
            [node, "-e", bootstrap + "\n" + script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_inspection_uses_actual_location_objects_and_states(self):
        self.run_node(r"""
const description=GENESIS_PLAYER_FEEDBACK.describeReceipt({node_receipts:[{
  status:'APPLIED',operation:'INSPECT',result:{inspection:{
    position:{x:1.25,y:-3},biome:'forest',world_settings:{time:'NIGHT',fog:0.48},
    nearby:[{kind:'lighthouse',concept:'Мой маяк',distance:4.2,interaction_state:{door_open:false,beacon_lit:false}}]
  }}
}]});
const text=description.paragraphs.join(' ');
assert.match(text,/лес/);
assert.match(text,/x 1,25, y -3/);
assert.match(text,/Мой маяк — 4,2 м/);
assert.match(text,/дверь закрыта, огонь погашен/);
assert.match(text,/ночь/);
assert(!text.includes('замок'));
const empty=GENESIS_PLAYER_FEEDBACK.describeReceipt({node_receipts:[{
  status:'APPLIED',operation:'INSPECT',result:{inspection:{position:{x:0,y:0},biome:'meadow',nearby:[]}}
}]});
assert.match(empty.paragraphs.join(' '),/не обнаружил объектов/);
""")

    def test_partial_execution_and_failures_do_not_claim_total_success(self):
        self.run_node(r"""
const f=GENESIS_PLAYER_FEEDBACK;
const partial=f.describeReceipt({node_receipts:[
  {status:'APPLIED',operation:'GENERATE_STRUCTURE',result:{mutation:{concept:'Дом',x:3,y:5}}},
  {status:'FAILED',operation:'AUDIO_CUE',reason:'AUDIO_DISABLED'},
  {status:'SKIPPED_DEPENDENCY',operation:'SPATIAL_RELATION'}
]});
assert.equal(partial.title,'Выполнена часть команды');
assert.equal(partial.status,'partial');
assert.match(partial.paragraphs.join(' '),/1 из 3/);
assert.match(partial.paragraphs.join(' '),/Звук выключен/);
const group=f.describeFailure('GROUP_PARTIAL_FAILURE:2/5',{materialized:2,requested:5});
assert.match(group.paragraphs.join(' '),/2 из 5/);
const unresolved=f.describeFailure('LOCAL_DEGRADED_NEEDS_JANUS_SEMANTIC_COMPILER');
assert.equal(unresolved.title,'Не удалось понять команду');
assert(unresolved.suggestions.some(suggestion=>suggestion.text==='осмотри место'));
assert.match(f.describeFailure('TOO_FAR',{interaction:{distance:8}}).paragraphs.join(' '),/8 м/);
assert.equal(f.describeFailure('ALREADY_DARK').title,'Маяк уже погашен');
assert.match(f.describeFailure('ACTION_BLOCKED').paragraphs.join(' '),/Проход перекрыт/);
""")

    def test_approach_only_claims_arrival_when_distance_confirms_it(self):
        self.run_node(r"""
const f=GENESIS_PLAYER_FEEDBACK,node={params:{action:'APPROACH'}};
const walking=f.describeNode({status:'APPLIED',operation:'INTERACT',result:{
  message:'Ты идёшь к двери маяка. Стрелки останавливают подход.',interaction:{name:'маяк',distance:8}
}},node);
assert.equal(walking.title,'Идёшь к маяку');
assert(!walking.paragraphs.join(' ').includes('Ты рядом'));
assert(!walking.suggestions.some(suggestion=>suggestion.text==='открой дверь'));
const near=f.describeNode({status:'APPLIED',operation:'INTERACT',result:{interaction:{name:'маяк',distance:0.95}}},node);
assert.equal(near.title,'Ты у двери маяка');
assert(near.suggestions.some(suggestion=>suggestion.text==='открой дверь'));
const unknown=f.describeNode({status:'APPLIED',operation:'INTERACT',result:{}},node);
assert.equal(unknown.title,'Подход к маяку');
const moved=f.describeNode({status:'APPLIED',operation:'MOVE',result:{moved:0.7,blocked:true}},{params:{direction:'FORWARD'}},{before:{player_position:{x:0,y:0}},after:{player_position:{x:0,y:0.7}}});
assert.match(moved.paragraphs.join(' '),/0,7 м/);
assert.match(moved.paragraphs.join(' '),/проход перекрыт/);
""")

    def test_bridge_interactions_safe_dom_and_full_collapsed_receipt(self):
        self.run_node(r"""
(async()=>{
  const b=GENESIS_COMMAND_BRIDGE_V5;
  const commands=[
    ['подойди к маяку','APPROACH'],['открой дверь','OPEN_DOOR'],
    ['зажги маяк','LIGHT_BEACON'],['погаси маяк','EXTINGUISH_BEACON'],
    ['approach lighthouse','APPROACH'],['open door','OPEN_DOOR'],
    ['light beacon','LIGHT_BEACON'],['extinguish beacon','EXTINGUISH_BEACON']
  ];
  for(const [text,action] of commands){
    const node=b.localGraph(text).nodes[0];
    assert.equal(node.family,'NAVIGATION');assert.equal(node.operation,'INTERACT');assert.equal(node.params.action,action);
  }
  assert.equal(b.localGraph('открой дверь #lh-42').nodes[0].params.target_id,'lh-42');
  // Negated text must not be upgraded into the requested interaction.
  assert.notEqual(b.localGraph('не открывай дверь').nodes[0].operation,'INTERACT');
  const receipt=await b.executeText('осмотри место');
  assert.equal(receipt.node_receipts[0].operation,'INSPECT');
  const result=elements.get('action-result');
  assert.match(result.textContent,/<img src=x onerror=alert\(1\)>/);
  assert.match(result.textContent,/луг/);
  assert.equal(result.attributes['aria-live'],'polite');
  assert.equal(result.attributes['aria-busy'],'false');
  const details=result.children.find(child=>child.tagName==='details');
  assert(details&&!details.open);
  assert.deepEqual(JSON.parse(details.children[1].textContent),receipt);
  GENESIS_COMMAND_BRIDGE_V3.online=true;
  GENESIS_COMMAND_BRIDGE_V3.health={scene_graph_available:true};
  globalThis.fetch=()=>{throw new Error('Bounded local interaction unexpectedly called the server')};
  const interaction=await b.executeText('открой дверь');
  assert.equal(interaction.node_receipts[0].operation,'INTERACT');
})().catch(error=>{console.error(error);process.exitCode=1});
""", bridge=True)

    def test_bridge_remains_usable_without_optional_feedback_module(self):
        self.run_node(r"""
(async()=>{
  const receipt=await GENESIS_COMMAND_BRIDGE_V5.executeText('осмотри место');
  assert.equal(receipt.node_receipts.length,1);
  assert.match(elements.get('action-result').textContent,/Действие выполнено/);
})().catch(error=>{console.error(error);process.exitCode=1});
""", bridge=True, feedback=False)


if __name__ == "__main__":
    unittest.main()
