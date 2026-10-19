(() => {
  'use strict';
  function textTarget(target){return target instanceof HTMLInputElement||target instanceof HTMLTextAreaElement||target?.isContentEditable;}
  addEventListener('keydown',event=>{
    if(textTarget(event.target)||event.repeat||document.body?.dataset?.genesisDrawerOpen==='true'||event.target?.closest?.('button,a,summary,select,[role=button]'))return;
    const rt=globalThis.GENESIS_WORLD_RUNTIME_V5||globalThis.GENESIS_WORLD_RUNTIME_V4;if(!rt)return;
    if(event.code==='Space'){event.preventDefault();rt.jump?.();return;}
    if(event.code==='KeyE'){event.preventDefault();rt.leaveMark('PLAYER MARK');return;}
    if(event.code==='KeyR'){event.preventDefault();rt.returnToHearth();return;}
    if(event.code==='Digit1'){event.preventDefault();rt.setCamera('FIRST_PERSON');return;}
    if(event.code==='Digit3'){event.preventDefault();rt.setCamera('THIRD_PERSON');return;}
    if(event.code==='KeyI'){event.preventDefault();rt.setCamera('ISOMETRIC');return;}
    if(event.code==='Slash'){event.preventDefault();globalThis.GENESIS_COMMAND_BRIDGE_V3?.focusConsole?.(false);}
  },true);
  globalThis.GENESIS_HOTKEYS_V3=Object.freeze({movement:'KeyboardEvent.code: KeyW KeyA KeyS KeyD + arrows',jump:'Space physical key / JUMP text intent',actions:'KeyE mark / KeyR hearth / Enter command console',cameras:'Digit1 first person / Digit3 third person / KeyI isometric',layout_independent:true});
})();