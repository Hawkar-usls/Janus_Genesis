(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const runtime = () => globalThis.GENESIS_WORLD_RUNTIME_V5;
  const bridge = () => globalThis.GENESIS_COMMAND_BRIDGE_V5;
  const guideKey = 'janus.genesis.player_guide_hidden.v1';
  const mirrorNames = {ORIGIN:'Исток', JANUS_16:'16 цветов', NOCTURNE:'Ночь', AETHER:'Эфир', EMBER:'Угли'};
  const panels = ['settings-panel', 'chronicle-panel'];
  let activePanel = null;
  let restoreFocus = null;
  let commandBusy = false;
  let nearbyTarget = null;
  let interactionCommand = 'осмотри место';
  let guideDismissed = false;
  let inspected = false;

  try { guideDismissed = localStorage.getItem(guideKey) === 'true'; } catch {}
  $('objective-guide').hidden = guideDismissed;

  function setText(element, text) {
    if (element && element.textContent !== text) element.textContent = text;
  }

  function rememberGuide(hidden) {
    guideDismissed = hidden;
    $('objective-guide').hidden = hidden;
    try { localStorage.setItem(guideKey, String(hidden)); } catch {}
  }

  function syncConsoleHeight() {
    const forge = document.querySelector('.action-forge');
    if (forge) document.documentElement.style.setProperty('--player-console-height', `${Math.ceil(forge.getBoundingClientRect().height)}px`);
  }

  function focusable(panel) {
    return [...panel.querySelectorAll('button:not([disabled]):not([hidden]), a[href], input:not([disabled]):not([hidden]), textarea, summary, [tabindex="0"]')]
      .filter(node => node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');
  }

  function syncDrawerState() {
    const opened = panels.find(id => !$(id).hidden) || null;
    if (opened === activePanel) return;
    const previous = activePanel;
    activePanel = opened;
    $('drawer-backdrop').hidden = !opened;
    document.body.dataset.genesisDrawerOpen = opened ? 'true' : 'false';
    $('settings-toggle').setAttribute('aria-expanded', String(opened === 'settings-panel'));
    $('chronicle-toggle').setAttribute('aria-expanded', String(opened === 'chronicle-panel'));
    if (opened) {
      if (!previous) restoreFocus = document.activeElement;
      // Release held movement before a drawer receives focus.
      globalThis.dispatchEvent(new Event('blur'));
      requestAnimationFrame(() => {
        const panel = $(opened);
        (panel.querySelector('.close-drawer') || panel).focus({preventScroll:true});
      });
      syncCamera();
    } else if (previous && restoreFocus?.isConnected) {
      restoreFocus.focus({preventScroll:true});
      restoreFocus = null;
    }
  }

  function closeDrawers() {
    panels.forEach(id => { $(id).hidden = true; });
    syncDrawerState();
  }

  function toggleSettings() {
    const opening = $('settings-panel').hidden;
    closeDrawers();
    $('settings-panel').hidden = !opening;
    syncDrawerState();
  }

  $('settings-toggle').addEventListener('click', toggleSettings);
  // The runtime owns Chronicle's toggle and close handlers; only coordinate drawers here.
  $('chronicle-toggle').addEventListener('click', () => {
    if (!$('chronicle-panel').hidden) $('settings-panel').hidden = true;
    syncDrawerState();
  });
  $('drawer-backdrop').addEventListener('click', closeDrawers);
  panels.forEach(id => new MutationObserver(syncDrawerState).observe($(id), {attributes:true, attributeFilter:['hidden']}));
  document.addEventListener('keydown', event => {
    if (!activePanel) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeDrawers();
    } else if (event.key === 'Tab') {
      const elements = focusable($(activePanel));
      if (!elements.length) { event.preventDefault(); $(activePanel).focus(); return; }
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && (document.activeElement === first || document.activeElement === $(activePanel))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });

  async function executeCommand(text) {
    if (commandBusy || $('action-submit').disabled) return;
    if (!bridge()?.executeText) {
      setText($('action-result'), 'Мир ещё загружается. Попробуй через мгновение.');
      return;
    }
    commandBusy = true;
    document.querySelectorAll('[data-player-command], #world-interact').forEach(button => { button.disabled = true; });
    try {
      await bridge().executeText(text);
      if (/осмотри/.test(text)) inspected = true;
    } finally {
      commandBusy = false;
      document.querySelectorAll('[data-player-command], #world-interact').forEach(button => { button.disabled = false; });
      updateWorldContext();
      syncConsoleHeight();
    }
  }

  document.querySelectorAll('[data-player-command]').forEach(button => {
    button.addEventListener('click', () => executeCommand(button.dataset.playerCommand));
  });
  $('world-interact').addEventListener('click', () => executeCommand(interactionCommand));
  $('objective-dismiss').addEventListener('click', () => rememberGuide(true));
  $('objective-show').addEventListener('click', () => { rememberGuide(false); closeDrawers(); updateWorldContext(); });

  function updateWorldContext() {
    const rt = runtime();
    if (!rt) return;
    const interactions = rt.getNearbyInteractions?.() || [];
    nearbyTarget = interactions[0] || null;
    const state = rt.getCanonicalState();
    const lighthouses = (state.explicit_world_mutations || []).filter(item => item.type === 'GENERATED_STRUCTURE' && item.structure_kind === 'lighthouse');
    const complete = lighthouses.some(item => item.interaction_state?.beacon_lit || item.beacon_lit) || Boolean(nearbyTarget?.beacon_lit);
    $('objective-guide').dataset.complete = String(complete);
    setText($('objective-title'), complete ? 'Первый маяк горит' : 'Зажги свой первый маяк');
    let instruction = inspected ? 'Создай маяк — кнопкой ниже или своими словами.' : 'Осмотрись, создай маяк и подойди к его двери.';
    if (lighthouses.length) instruction = 'Подойди к маяку и открой его дверь.';
    if (nearbyTarget && nearbyTarget.distance <= 2.5 && !nearbyTarget.door_open) instruction = 'Ты у маяка. Открой дверь.';
    if (nearbyTarget?.door_open) instruction = 'Дверь открыта. Теперь зажги маяк.';
    if (complete) instruction = 'Твой свет останется в мире. Продолжай исследовать и создавать.';
    setText($('objective-step'), instruction);

    const welcomeOpen = !$('welcome').hidden;
    $('world-interaction').hidden = !nearbyTarget || welcomeOpen;
    if (!nearbyTarget) return;
    const distance = Number(nearbyTarget.distance) || 0;
    const distanceLabel = `${distance < 10 ? distance.toFixed(1) : Math.round(distance)} м`;
    if (distance > 2.5) {
      interactionCommand = 'подойди к маяку';
      setText($('world-interact'), 'Подойти к маяку');
      setText($('world-interaction-hint'), `Твой маяк · ${distanceLabel}`);
    } else if (!nearbyTarget.door_open) {
      interactionCommand = 'открой дверь';
      setText($('world-interact'), 'Открыть дверь');
      setText($('world-interaction-hint'), `Маяк рядом · ${distanceLabel}`);
    } else if (!nearbyTarget.beacon_lit) {
      interactionCommand = 'зажги маяк';
      setText($('world-interact'), 'Зажечь маяк');
      setText($('world-interaction-hint'), 'Дверь открыта. Пора зажечь свет.');
    } else {
      interactionCommand = 'осмотри место';
      setText($('world-interact'), 'Осмотреть маяк');
      setText($('world-interaction-hint'), 'Маяк горит. Свет виден издалека.');
    }
  }

  function syncCamera() {
    const view = runtime()?.getPresentationState();
    if (!view) return;
    document.querySelectorAll('[data-player-camera]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.playerCamera === view.camera_mode));
    });
    $('camera-distance').value = String(Math.round(view.camera_distance));
    $('camera-distance').disabled = view.camera_mode === 'FIRST_PERSON';
    setText($('camera-distance-value'), `${Math.round(view.camera_distance)} м`);
  }
  document.querySelectorAll('[data-player-camera]').forEach(button => {
    button.addEventListener('click', () => { runtime()?.setCamera(button.dataset.playerCamera); syncCamera(); });
  });
  $('camera-distance').addEventListener('input', () => {
    runtime()?.setCameraDistance($('camera-distance').value);
    setText($('camera-distance-value'), `${$('camera-distance').value} м`);
  });

  function localizeAudio() {
    const enabled = Boolean(globalThis.GENESIS_AUDIO_RUNTIME?.enabled);
    const blocked = /BLOCKED|UNAVAILABLE|Нет звука/.test($('audio-toggle').textContent);
    setText($('audio-toggle'), blocked ? 'Нет звука' : enabled ? 'Звук вкл' : 'Звук выкл');
    $('audio-toggle').setAttribute('aria-pressed', String(enabled));
    $('audio-toggle').setAttribute('aria-label', enabled ? 'Выключить звук' : 'Включить звук');
  }

  function localizeMirror() {
    const button = $('mirror-hardware-toggle');
    if (!button) return;
    const profile = globalThis.GENESIS_PLAYER_MIRROR_R0_7?.getProfile?.() || button.dataset.profile || 'ORIGIN';
    setText(button, `Вид: ${mirrorNames[profile] || profile}`);
    button.setAttribute('aria-label', `Стиль мира: ${mirrorNames[profile] || profile}. Нажми, чтобы сменить.`);
    button.title = 'Сменить визуальный стиль мира';
  }

  new MutationObserver(localizeAudio).observe($('audio-toggle'), {childList:true, characterData:true, subtree:true});
  if ($('mirror-hardware-toggle')) new MutationObserver(localizeMirror).observe($('mirror-hardware-toggle'), {childList:true, characterData:true, subtree:true});
  addEventListener('genesis:mirror-changed', localizeMirror);
  addEventListener('genesis:command-complete', event => {
    if (event.detail?.receipt?.node_receipts?.some(node => node.operation === 'INSPECT' && node.status === 'APPLIED')) inspected = true;
    updateWorldContext();
    syncConsoleHeight();
  });
  document.addEventListener('genesis:navigation-stop', event => {
    if (event.detail?.message) setText($('action-result'), event.detail.message);
    updateWorldContext();
    syncConsoleHeight();
  });
  if (globalThis.ResizeObserver) new ResizeObserver(syncConsoleHeight).observe(document.querySelector('.action-forge'));
  addEventListener('resize', syncConsoleHeight);
  globalThis.visualViewport?.addEventListener('resize', syncConsoleHeight);
  $('enter-world').addEventListener('click', () => { updateWorldContext(); syncConsoleHeight(); });

  // Birth is injected by the causal lifecycle module before this shell loads.
  const birth = $('genesis-birth-veil');
  if (birth) {
    setText(birth.querySelector('.genesis-birth-eyebrow'), 'GENESIS · НАЧАЛО ТВОЕГО МИРА');
    setText(birth.querySelector('.genesis-birth-card p'), 'Опиши первое место или событие. Попробуй «построй старый каменный маяк» — или начни со своей идеи. После этого можно будет войти в мир и продолжить.');
    setText(birth.querySelector('.genesis-birth-law'), 'Создавай словами · исследуй шаг за шагом');
  }
  localizeAudio();
  localizeMirror();
  syncCamera();
  syncConsoleHeight();
  updateWorldContext();
  setInterval(() => {
    if (!document.hidden) {
      updateWorldContext();
      if (activePanel === 'settings-panel') syncCamera();
    }
  }, 350);
  globalThis.GENESIS_PLAYER_UI = Object.freeze({version:'1.0.0', updateWorldContext, closeDrawers});
})();
