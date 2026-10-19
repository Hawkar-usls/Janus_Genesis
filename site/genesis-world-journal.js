(() => {
  'use strict';

  const SAVE_KEY = 'janus.genesis.world_shell_r0.save.v1';
  const BIRTH_KEY = 'janus.genesis.birth_r0_6.v1';
  const PENDING_KEY = 'janus.genesis.birth_r0_6.pending_intent.v1';
  const BACKUP_KEY = 'janus.genesis.browser_import.backup.v1';
  const FORMAT = 'janus.genesis.browser_export.v1';
  const WORLD_ID = 'GENESIS_ONE_WORLD_R0';
  const WORLD_SEED = 'genesis-one-world-r0';
  const MAX_BYTES = 2 * 1024 * 1024;
  const unsafeKeys = new Set(['__proto__', 'prototype', 'constructor']);
  const saveKeys = new Set(['schema', 'generator_version', 'runtime_version', 'world_id', 'world_seed', 'player_position', 'mirror_profile', 'presentation_dimension', 'camera_mode', 'camera_heading', 'camera_pitch', 'camera_roll', 'camera_distance', 'world_settings', 'discovered_chunk_coordinates', 'explicit_world_mutations', 'chronicle_hash_chain', 'birth_state', 'birth_sentinel', 'birth_version', 'birth_seed', 'birth_intent_sha256']);
  const mutationKeys = new Set(['type', 'id', 'x', 'y', 'label', 'created_at', 'concept', 'structure_kind', 'entity_kind', 'transform_kind', 'seed', 'recipe', 'mechanics', 'asset_refs', 'janus_receipt_hash', 'radius', 'amount', 'action_forge', 'entry_heading', 'interaction_state']);
  const mechanicKinds = new Set(['HINGE', 'DOOR', 'ELEVATOR', 'ROTATOR', 'OSCILLATOR', 'PARTICLE_EMITTER', 'BREAKABLE', 'BUOYANT', 'VEHICLE_WHEEL', 'NPC_PATH', 'TRIGGER_ZONE', 'ANIMATION_CLIP', 'COLLIDER_PROFILE']);
  let staged = null;
  let requestNumber = 0;
  let committing = false;
  const $ = id => document.getElementById(id);
  const fail = message => { throw new Error(message); };
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const text = (value, max = 256) => typeof value === 'string' && value.length <= max;
  const finite = (value, max = 10000000) => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= max;
  const shaPattern = /^[a-f0-9]{64}$/;
  const hashPattern = /^(?:[a-f0-9]{64}|[a-f0-9]{8}|fnv1a32-[a-f0-9]{8})$/;
  const bytes = value => new TextEncoder().encode(value).byteLength;
  const copy = value => JSON.parse(JSON.stringify(value));

  function stable(value) {
    if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
    if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`;
    return JSON.stringify(value);
  }

  function fnv(value) {
    let hash = 0x811c9dc5;
    for (let index = 0; index < value.length; index++) { hash ^= value.charCodeAt(index); hash = Math.imul(hash, 0x01000193); }
    return (hash >>> 0).toString(16).padStart(8, '0');
  }

  async function sha(value) {
    if (!globalThis.crypto?.subtle) fail('Браузер не поддерживает проверку целостности файла. Открой Genesis по HTTPS.');
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  }

  // Inspect parsed JSON before using a property or creating a new world object.
  function checkTree(value, depth = 0, budget = {nodes: 0}) {
    if (++budget.nodes > 100000 || depth > 14) fail('В файле слишком сложная структура.');
    if (typeof value === 'number' && !Number.isFinite(value)) fail('В файле есть некорректное число.');
    if (typeof value === 'string' && value.length > 8192) fail('В файле есть слишком длинное поле.');
    if (value === null || typeof value !== 'object') return;
    for (const key of Object.keys(value)) {
      if (unsafeKeys.has(key)) fail('В файле есть недопустимое поле.');
      if (/(?:^|_)(?:token|password|secret|authorization|api_key|endpoint|base_url|binary|base64)(?:_|$)/i.test(key)) fail('Файл содержит настройки подключения или внешние данные вместо сохранения мира.');
      checkTree(value[key], depth + 1, budget);
    }
  }

  function fields(value, allowed, message) {
    if (!object(value) || Object.keys(value).some(key => !allowed.has(key))) fail(message);
  }

  function pair(value, integer = false) {
    return Array.isArray(value) && value.length === 2 && value.every(number => finite(number) && (!integer || Number.isInteger(number)));
  }

  function validateAssets(refs) {
    if (refs === undefined) return;
    if (!Array.isArray(refs) || refs.length > 8) fail('Слишком много материалов у объекта.');
    for (const ref of refs) {
      if (!object(ref) || !text(ref.provider_id, 160) || !text(ref.asset_id, 256) || !text(ref.rights, 80)) fail('Некорректная ссылка на материал.');
      // The portable format keeps attribution metadata, never remote endpoints or binaries.
      fields(ref, new Set(['provider_id', 'asset_id', 'rights', 'name', 'author', 'attribution_required', 'source_url', 'license_url']), 'Материал содержит внешние данные, которые нельзя загрузить из сохранения.');
      for (const key of ['name', 'author']) if (ref[key] !== undefined && !text(ref[key], 512)) fail('Некорректная подпись материала.');
      if (ref.attribution_required !== undefined && typeof ref.attribution_required !== 'boolean') fail('Некорректные условия материала.');
      for (const key of ['source_url', 'license_url']) if (ref[key] !== undefined) {
        if (!text(ref[key], 1000)) fail('Некорректный адрес источника материала.');
        if (ref[key]) { let url; try { url = new URL(ref[key]); } catch { fail('Некорректный адрес источника материала.'); }
          if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) fail('Адрес материала содержит параметры подключения.'); }
      }
    }
  }

  async function validateChronicle(events) {
    if (!Array.isArray(events) || events.length > 3072) fail('Слишком большая или некорректная история мира.');
    let previous = null;
    for (const event of events) {
      if (!object(event) || !Number.isSafeInteger(event.sequence) || event.sequence < 1 || !text(event.type, 80) || !/^[A-Z][A-Z0-9_]*$/.test(event.type) || !hashPattern.test(event.event_hash || '')) fail('Некорректная запись истории.');
      if (previous && event.sequence !== previous.sequence + 1) fail('Нарушен порядок событий в истории.');
      let source;
      if (Object.hasOwn(event, 'prev')) {
        fields(event, new Set(['sequence', 'type', 'data', 'prev', 'event_hash']), 'Некорректный формат события.');
        if (!object(event.data)) fail('Некорректные данные события.');
        if (event.prev !== (previous?.event_hash || (event.sequence === 1 ? 'GENESIS' : event.prev)) || (event.sequence > 1 && !previous && !hashPattern.test(event.prev || ''))) fail('Нарушена связь событий в истории.');
        source = JSON.stringify({sequence: event.sequence, type: event.type, data: event.data, prev: event.prev});
      } else {
        if (!Object.hasOwn(event, 'previous_hash') || event.previous_hash !== (previous?.event_hash || (event.sequence === 1 ? 'GENESIS_ORIGIN' : event.previous_hash)) || (event.sequence > 1 && !previous && !hashPattern.test(event.previous_hash || ''))) fail('Нарушена связь событий в истории.');
        const {event_hash, ...core} = event;
        source = stable(core);
      }
      const actual = event.event_hash.length === 64 ? await sha(source) : `${event.event_hash.startsWith('fnv1a32-') ? 'fnv1a32-' : ''}${fnv(source)}`;
      if (actual !== event.event_hash) fail('История изменена или файл повреждён: проверка целостности не пройдена.');
      previous = event;
    }
  }

  const eventData = event => object(event.data) ? event.data : event;
  const samePlace = (data, mutation) => {
    const x = data.x ?? data.position?.[0], y = data.y ?? data.position?.[1];
    return finite(x) && finite(y) && Math.abs(x - mutation.x) <= .00501 && Math.abs(y - mutation.y) <= .00501;
  };

  function validateMutation(mutation, events) {
    fields(mutation, mutationKeys, 'Неизвестный формат объекта мира.');
    if (!['PLAYER_MARK', 'GENERATED_STRUCTURE', 'SPAWNED_ENTITY', 'WORLD_TRANSFORM'].includes(mutation.type) || !finite(mutation.x) || !finite(mutation.y)) fail('Некорректный объект или его положение.');
    for (const key of ['id', 'label', 'concept', 'structure_kind', 'entity_kind', 'transform_kind', 'seed', 'recipe']) if (mutation[key] !== undefined && !text(mutation[key], key === 'recipe' ? 256 : 160)) fail('Некорректное описание объекта.');
    if (mutation.created_at !== undefined && (!finite(mutation.created_at, 100000000000000) || mutation.created_at < 0)) fail('Некорректное время создания объекта.');
    if (mutation.entry_heading !== undefined && !finite(mutation.entry_heading)) fail('Некорректное направление входа.');
    validateAssets(mutation.asset_refs);
    if (mutation.janus_receipt_hash !== undefined && mutation.janus_receipt_hash !== null && !hashPattern.test(mutation.janus_receipt_hash)) fail('Некорректный след создания объекта.');
    if (mutation.mechanics !== undefined) {
      if (!Array.isArray(mutation.mechanics) || mutation.mechanics.length > 16) fail('Некорректные механики объекта.');
      for (const mechanic of mutation.mechanics) {
        fields(mechanic, new Set(['schema', 'kind', 'params', 'source', 'remote_code_executed']), 'Некорректная механика объекта.');
        if (mechanic.schema !== 'janus.genesis.mechanic_recipe.v1' || !mechanicKinds.has(mechanic.kind) || mechanic.remote_code_executed !== false || !text(mechanic.source, 160) || !object(mechanic.params) || Object.keys(mechanic.params).length > 32) fail('Неизвестная механика объекта.');
        if (Object.entries(mechanic.params).some(([key, value]) => !/^[a-zA-Z][a-zA-Z0-9_]{0,47}$/.test(key) || !(value === null || typeof value === 'boolean' || text(value, 160) || finite(value)))) fail('Некорректные параметры механики.');
      }
    }
    if (mutation.action_forge !== undefined) {
      fields(mutation.action_forge, new Set(['schema', 'intent', 'concept', 'action_seed', 'source_text']), 'Некорректная причина метки.');
      if (mutation.action_forge.schema !== 'janus.genesis.action_intent.v1' || !['PLACE_MARK', 'PLACE_ACTION_ANCHOR'].includes(mutation.action_forge.intent) || !text(mutation.action_forge.concept, 160) || !text(mutation.action_forge.source_text, 280) || !text(mutation.action_forge.action_seed, 160)) fail('Некорректная причина метки.');
    }
    if (mutation.type === 'GENERATED_STRUCTURE' && (!text(mutation.structure_kind, 64) || !mutation.structure_kind || !text(mutation.seed, 160))) fail('Неизвестная постройка.');
    if (mutation.type === 'SPAWNED_ENTITY' && (!text(mutation.entity_kind, 64) || !mutation.entity_kind || !text(mutation.seed, 160))) fail('Неизвестный обитатель.');
    if (mutation.type === 'WORLD_TRANSFORM' && (!['RAISE_HILL', 'LOWER_GROUND'].includes(mutation.transform_kind) || !finite(mutation.radius, 16) || mutation.radius < 1 || !finite(mutation.amount, 8) || mutation.amount < .1)) fail('Некорректное изменение земли.');
    const expected = {GENERATED_STRUCTURE: ['STRUCTURE_MATERIALIZED'], SPAWNED_ENTITY: ['ENTITY_SPAWNED'], WORLD_TRANSFORM: ['WORLD_TRANSFORMED'], PLAYER_MARK: ['PLAYER_MARK', 'PLAYER_MARK_PLACED', 'ACTION_ANCHOR_PLACED']}[mutation.type];
    const creation = events.find(event => {
      if (!expected.includes(event.type)) return false;
      const data = eventData(event);
      if (!samePlace(data, mutation)) return false;
      if (mutation.type === 'GENERATED_STRUCTURE' && data.kind !== mutation.structure_kind) return false;
      if (mutation.type === 'GENERATED_STRUCTURE' && ((data.concept !== undefined && data.concept !== mutation.concept) || (data.recipe !== undefined && data.recipe !== mutation.recipe))) return false;
      if (mutation.type === 'SPAWNED_ENTITY' && data.kind !== mutation.entity_kind) return false;
      if (mutation.type === 'WORLD_TRANSFORM' && (data.kind !== mutation.transform_kind || data.radius !== mutation.radius || data.amount !== mutation.amount)) return false;
      return (!data.mutation_id || data.mutation_id === mutation.id) && (!data.target_id || data.target_id === mutation.id);
    });
    if (!creation) fail('У объекта нет подтверждённого события создания в истории. Дождись завершения действия и попробуй снова.');
    if (mutation.interaction_state !== undefined) {
      fields(mutation.interaction_state, new Set(['door_open', 'beacon_lit']), 'Некорректное состояние маяка.');
      if (mutation.structure_kind !== 'lighthouse' || !text(mutation.id, 160) || !mutation.id || typeof mutation.interaction_state.door_open !== 'boolean' || typeof mutation.interaction_state.beacon_lit !== 'boolean') fail('Некорректное состояние маяка.');
      const interactions = events.filter(event => ['LIGHTHOUSE_DOOR_OPENED', 'BEACON_LIT', 'BEACON_EXTINGUISHED'].includes(event.type) && eventData(event).target_id === mutation.id);
      if (interactions.some(event => !samePlace(eventData(event), mutation))) fail('Событие маяка связано с другим местом.');
      const initial = eventData(creation).initial_interaction_state;
      if (initial !== undefined) {
        fields(initial, new Set(['door_open', 'beacon_lit']), 'Некорректное исходное состояние маяка.');
        if (typeof initial.door_open !== 'boolean' || typeof initial.beacon_lit !== 'boolean') fail('Некорректное исходное состояние маяка.');
      }
      const door = initial?.door_open === true || interactions.some(event => event.type === 'LIGHTHOUSE_DOOR_OPENED');
      const lastBeacon = interactions.filter(event => event.type !== 'LIGHTHOUSE_DOOR_OPENED').at(-1);
      // Before explicit interactions existed, generated lighthouses were already lit.
      const initialBeacon = initial ? initial.beacon_lit : !Object.hasOwn(eventData(creation), 'created_at');
      const beacon = lastBeacon ? lastBeacon.type === 'BEACON_LIT' : initialBeacon;
      if (mutation.interaction_state.door_open !== door || mutation.interaction_state.beacon_lit !== beacon) fail('Состояние маяка не совпадает с его историей.');
    }
  }

  function deriveBirth(save) {
    const births = save.chronicle_hash_chain.filter(event => event.type === 'GENESIS_BIRTH');
    if (births.length > 1) fail('В истории больше одного рождения мира.');
    if (births.length) {
      const birth = births[0], data = eventData(birth);
      if (save.chronicle_hash_chain[0] !== birth || birth.sequence !== 1 || birth.prev !== 'GENESIS' || !shaPattern.test(data.birth_seed || '') || !shaPattern.test(data.intent_sha256 || '') || !Number.isInteger(data.intent_length) || data.intent_length < 1 || data.intent_length > 4000 || !pair(data.origin_chunk, true) || data.origin_chunk[0] !== 0 || data.origin_chunk[1] !== 0 || save.birth_sentinel || (save.birth_state !== undefined && save.birth_state !== 'BORN_R0_6') || (save.birth_seed !== undefined && save.birth_seed !== data.birth_seed) || (save.birth_intent_sha256 !== undefined && save.birth_intent_sha256 !== data.intent_sha256)) fail('Не удалось подтвердить исходное рождение мира.');
      return {schema: 'janus.genesis.birth_state.v1', version: '0.6.0', world_id: WORLD_ID, state: 'BORN_R0_6', birth_seed: data.birth_seed, intent_sha256: data.intent_sha256, event_hash: birth.event_hash};
    }
    if (save.birth_state === 'BORN_R0_6' || save.birth_seed || save.birth_intent_sha256) fail('В файле отсутствует исходное событие рождения мира.');
    if (save.birth_sentinel || save.birth_state === 'UNBORN_BOOT_SENTINEL') {
      if (save.birth_sentinel !== true || save.birth_state !== 'UNBORN_BOOT_SENTINEL' || save.chronicle_hash_chain.length || save.explicit_world_mutations.length) fail('Некорректное начальное состояние мира.');
      return {schema: 'janus.genesis.birth_state.v1', version: '0.6.0', world_id: WORLD_ID, state: 'UNBORN', boot_sentinel: true};
    }
    if (save.birth_state !== undefined && save.birth_state !== 'BORN_LEGACY_R0_5') fail('Неизвестное состояние рождения мира.');
    return {schema: 'janus.genesis.birth_state.v1', version: '0.6.0', world_id: WORLD_ID, state: 'BORN_LEGACY_R0_5', migration: true, retroactive_birth_claim: false};
  }

  async function validateSave(save) {
    checkTree(save);
    fields(save, saveKeys, 'Это не поддерживаемое сохранение Genesis.');
    if (save.schema !== 'janus.genesis.world_shell_save.v1' || save.world_id !== WORLD_ID || save.world_seed !== WORLD_SEED || !text(save.generator_version, 120)) fail('Этот файл относится к другому миру или версии Genesis.');
    for (const key of ['runtime_version', 'birth_version']) if (save[key] !== undefined && !text(save[key], 80)) fail('Некорректная версия сохранения.');
    fields(save.player_position, new Set(['x', 'y']), 'Некорректное положение игрока.');
    if (!finite(save.player_position.x) || !finite(save.player_position.y)) fail('Некорректное положение игрока.');
    if (save.mirror_profile !== undefined && !['ORIGIN', 'NOCTURNE', 'AETHER', 'EMBER'].includes(save.mirror_profile)) fail('Неизвестный облик мира.');
    if (save.camera_mode !== undefined && !['FIRST_PERSON', 'THIRD_PERSON', 'ISOMETRIC'].includes(save.camera_mode)) fail('Неизвестный вид камеры.');
    if (save.presentation_dimension !== undefined && !['2D', '3D'].includes(save.presentation_dimension)) fail('Неизвестное измерение мира.');
    for (const key of ['camera_heading', 'camera_pitch', 'camera_roll', 'camera_distance']) if (save[key] !== undefined && !finite(save[key])) fail('Некорректные настройки камеры.');
    if (save.world_settings !== undefined) {
      fields(save.world_settings, new Set(['time', 'fog', 'weather']), 'Некорректные настройки мира.');
      if ((save.world_settings.time !== undefined && !text(save.world_settings.time, 32)) || (save.world_settings.weather !== undefined && !text(save.world_settings.weather, 32)) || (save.world_settings.fog !== undefined && (!finite(save.world_settings.fog, .85) || save.world_settings.fog < 0))) fail('Некорректная погода мира.');
    }
    if (!Array.isArray(save.discovered_chunk_coordinates) || save.discovered_chunk_coordinates.length > 8192 || save.discovered_chunk_coordinates.some(chunk => !pair(chunk, true))) fail('Некорректная карта открытых мест.');
    if (!Array.isArray(save.explicit_world_mutations) || save.explicit_world_mutations.length > 768) fail('Слишком много объектов или некорректный список объектов.');
    await validateChronicle(save.chronicle_hash_chain);
    const ids = new Set();
    for (const mutation of save.explicit_world_mutations) {
      validateMutation(mutation, save.chronicle_hash_chain);
      if (mutation.id) { if (ids.has(mutation.id)) fail('В мире повторяется идентификатор объекта.'); ids.add(mutation.id); }
    }
    return {save, birth: deriveBirth(save)};
  }

  function portableSave(original) {
    const save = {};
    for (const key of saveKeys) if (Object.hasOwn(original, key)) save[key] = copy(original[key]);
    for (const mutation of save.explicit_world_mutations || []) if (Array.isArray(mutation.asset_refs)) {
      mutation.asset_refs = mutation.asset_refs.map(ref => {
        const clean = {};
        for (const key of ['provider_id', 'asset_id', 'rights', 'name', 'author', 'attribution_required']) if (Object.hasOwn(ref, key)) clean[key] = copy(ref[key]);
        for (const key of ['source_url', 'license_url']) if (typeof ref[key] === 'string') { try { const url = new URL(ref[key]); if (url.protocol === 'https:' && !url.username && !url.password) { url.search = ''; url.hash = ''; clean[key] = url.href; } } catch {} }
        return clean;
      });
    }
    return save;
  }

  async function exportText() {
    const runtime = globalThis.GENESIS_WORLD_RUNTIME_V5;
    if (runtime?.flushSave && await runtime.flushSave() === false) fail('Браузер не смог сохранить последние действия. Сначала освободи место на устройстве.');
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) fail('Пока нет сохранённого мира. Создай его и попробуй снова.');
    if (bytes(raw) > MAX_BYTES) fail('Мир превышает размер переносимого файла — 2 МБ.');
    let original; try { original = JSON.parse(raw); } catch { fail('Не удалось прочитать сохранение на этом устройстве.'); }
    checkTree(original);
    const save = portableSave(original);
    await validateSave(save);
    const result = JSON.stringify({schema: FORMAT, exported_at: new Date().toISOString(), world_id: WORLD_ID, world_seed: WORLD_SEED, save_sha256: await sha(JSON.stringify(save)), save}, null, 2);
    if (bytes(result) > MAX_BYTES) fail('Мир превышает размер переносимого файла — 2 МБ.');
    return result;
  }

  async function parseImport(raw) {
    if (typeof raw !== 'string' || bytes(raw) > MAX_BYTES) fail('Файл слишком большой. Максимум — 2 МБ.');
    let parsed; try { parsed = JSON.parse(raw); } catch { fail('Не удалось прочитать JSON. Выбери файл мира, скачанный из Genesis.'); }
    checkTree(parsed);
    let save = parsed;
    if (parsed?.schema === FORMAT) {
      fields(parsed, new Set(['schema', 'exported_at', 'world_id', 'world_seed', 'save_sha256', 'save']), 'Неизвестный формат переносимого файла.');
      if (parsed.world_id !== WORLD_ID || parsed.world_seed !== WORLD_SEED || !shaPattern.test(parsed.save_sha256 || '') || !text(parsed.exported_at, 80) || !Number.isFinite(Date.parse(parsed.exported_at))) fail('Файл относится к другому миру или повреждён.');
      if (await sha(JSON.stringify(parsed.save)) !== parsed.save_sha256) fail('Файл изменён или повреждён: контрольная сумма не совпадает.');
      save = parsed.save;
    }
    const validated = await validateSave(save);
    return {save: copy(validated.save), birth: copy(validated.birth)};
  }

  function message(value) { const node = $('save-import-status'); if (node) node.textContent = value; }
  function buttons(show) { for (const id of ['save-import-confirm', 'save-import-cancel']) { const node = $(id); if (node) node.hidden = !show; } }
  function cancelImport() { if (committing) return; requestNumber++; staged = null; buttons(false); if ($('save-import')) $('save-import').value = ''; message('Загрузка отменена. Текущий мир сохранён.'); }

  async function stageImportText(raw) {
    if (committing) fail('Дождись завершения загрузки мира.');
    const request = ++requestNumber;
    staged = null; buttons(false); message('Проверяем файл и историю мира…');
    try {
      const result = await parseImport(raw);
      if (request !== requestNumber) return null;
      staged = result;
      const save = result.save, at = save.player_position;
      message(`Файл проверен: объектов — ${save.explicit_world_mutations.length}, событий — ${save.chronicle_hash_chain.length}, открытых мест — ${save.discovered_chunk_coordinates.length}. Позиция: ${at.x.toFixed(1)}, ${at.y.toFixed(1)}. Кнопка «Заменить текущий мир» загрузит этот мир; текущая версия останется в резервной копии на устройстве.`);
      buttons(true);
      return {objects: save.explicit_world_mutations.length, events: save.chronicle_hash_chain.length, chunks: save.discovered_chunk_coordinates.length};
    } catch (error) {
      if (request === requestNumber) message(error.message || 'Не удалось проверить файл мира.');
      throw error;
    }
  }

  function restoreStorage(key, value) { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); }

  function importBusy(busy) {
    for (const id of ['save-import', 'save-import-confirm', 'save-import-cancel']) {
      const node = $(id); if (node) node.disabled = busy;
    }
  }

  async function confirmImport() {
    if (!staged || committing) return false;
    committing = true;
    importBusy(true);
    message('Сохраняем последние действия перед загрузкой мира…');
    const old = {};
    let writesStarted = false;
    let resumeSaveWrites = null;
    try {
      const runtime = globalThis.GENESIS_WORLD_RUNTIME_V5;
      // Block new mutations, finish pending Chronicle hashes, and fence writes
      // before capturing a complete backup or changing any imported state.
      if (runtime?.beginWorldReplacement) {
        const resume = await runtime.beginWorldReplacement();
        if (typeof resume !== 'function') fail('Не удалось подготовить текущий мир к замене.');
        resumeSaveWrites = resume;
      } else {
        resumeSaveWrites = runtime?.pauseSaveWrites?.() || null;
      }
      for (const key of [SAVE_KEY, BIRTH_KEY, BACKUP_KEY]) old[key] = localStorage.getItem(key);
      if (old[SAVE_KEY] && bytes(old[SAVE_KEY]) > MAX_BYTES) fail('Текущий мир слишком большой для резервной копии. Замена отменена.');
      if (old[BIRTH_KEY] && bytes(old[BIRTH_KEY]) > 16384) fail('Не удалось создать резервную копию состояния мира. Замена отменена.');
      const backup = JSON.stringify({schema: 'janus.genesis.browser_import.backup.v1', created_at: new Date().toISOString(), save_text: old[SAVE_KEY], birth_text: old[BIRTH_KEY]});
      // Keeping a single previous version bounds storage growth; no save is changed before this succeeds.
      localStorage.setItem(BACKUP_KEY, backup);
      writesStarted = true;
      localStorage.setItem(BIRTH_KEY, JSON.stringify(staged.birth));
      const next = JSON.stringify(staged.save);
      localStorage.setItem(SAVE_KEY, next);
      if (localStorage.getItem(SAVE_KEY) !== next) fail('Браузер не подтвердил запись мира.');
    } catch (error) {
      if (writesStarted) {
        try { for (const key of [SAVE_KEY, BIRTH_KEY, BACKUP_KEY]) restoreStorage(key, old[key]); }
        catch { resumeSaveWrites?.(); message('Браузер не смог завершить загрузку. Предыдущая версия мира находится в резервной копии на этом устройстве.'); committing = false; importBusy(false); return false; }
      }
      committing = false;
      importBusy(false);
      resumeSaveWrites?.();
      message(`Не удалось заменить мир. Текущий мир сохранён. ${error.message || 'Проверь свободное место в браузере.'}`);
      return false;
    }
    try { sessionStorage.removeItem(PENDING_KEY); } catch {}
    staged = null; buttons(false); message('Мир загружен. Открываем его…');
    globalThis.location.reload();
    return true;
  }

  const kinds = {lighthouse: 'маяк', house: 'дом', castle: 'замок', tower: 'башня', portal: 'портал', bridge: 'мост', wall: 'стена', statue: 'статуя', tree: 'дерево', generic_structure: 'постройка', generic_entity: 'обитатель'};
  function describeEvent(event) {
    const data = eventData(event);
    const concept = text(data.concept, 160) && data.concept ? `«${data.concept}»` : kinds[data.kind] || 'объект';
    const directions = {N: 'на север', NE: 'на северо-восток', E: 'на восток', SE: 'на юго-восток', S: 'на юг', SW: 'на юго-запад', W: 'на запад', NW: 'на северо-запад', FORWARD: 'вперёд', BACKWARD: 'назад'};
    const titles = {
      GENESIS_BIRTH: ['Мир появился', 'Первая причина принята. С неё начинается история этого мира.'],
      CHUNK_DISCOVERED: ['Открыто новое место', pair(data.chunk, true) ? `Участок карты ${data.chunk[0]}, ${data.chunk[1]} теперь известен.` : 'На карте появилось новое известное место.'],
      STRUCTURE_MATERIALIZED: ['Появилась постройка', `Создан ${concept}.`],
      ENTITY_SPAWNED: ['Появился обитатель', `Рядом появился ${kinds[data.kind] || data.kind || 'новый обитатель'}.`],
      PLAYER_MARK: ['Оставлен знак', data.label && data.label !== 'PLAYER MARK' ? `Твой знак: «${data.label}».` : 'Ты оставил знак в этом месте.'],
      PLAYER_MARK_PLACED: ['Оставлен знак', 'Ты оставил знак в этом месте.'],
      ACTION_ANCHOR_PLACED: ['Создан памятный знак', 'Твоё намерение стало знаком в мире.'],
      TEXT_MOVE: ['Сделан шаг', `Ты прошёл ${directions[data.direction] || 'дальше'}${finite(data.steps, 64) ? ` на ${data.steps} м` : ''}.`],
      RETURN_TO_HEARTH: ['Возвращение к очагу', 'Ты снова у начала своего пути.'],
      ATMOSPHERE_CHANGED: ['Изменилась атмосфера', `${data.time === 'NIGHT' ? 'Наступила ночь.' : data.time === 'DAY' ? 'Наступил день.' : 'Мир сменил настроение.'}${finite(data.fog, .85) && data.fog > .3 ? ' Место укрыл туман.' : ''}`],
      WORLD_TRANSFORMED: ['Изменилась земля', data.kind === 'LOWER_GROUND' ? 'В этом месте земля опустилась.' : 'В этом месте поднялся холм.'],
      LIGHTHOUSE_DOOR_OPENED: ['Открыта дверь маяка', 'Вход открыт. Можно подойти к огню маяка.'],
      LIGHTHOUSE_APPROACHED: ['Ты у маяка', 'Теперь можно открыть его дверь и зажечь огонь.'],
      BEACON_LIT: ['Зажжён огонь маяка', 'Маяк светит. Это место теперь легче узнать издалека.'],
      BEACON_EXTINGUISHED: ['Погашен огонь маяка', 'Огонь маяка погас. Его можно зажечь снова.']
    };
    const [title, description] = titles[event.type] || ['Мир запомнил действие', 'В истории появилась новая запись.'];
    let position = '';
    const x = data.x ?? data.position?.[0], y = data.y ?? data.position?.[1];
    if (finite(x) && finite(y)) position = `Место: ${x.toFixed(1)}, ${y.toFixed(1)}.`;
    const timestamp = data.created_at ?? event.created_at ?? event.timestamp;
    let time = '';
    if ((typeof timestamp === 'number' || typeof timestamp === 'string') && Number.isFinite(new Date(timestamp).getTime())) time = new Date(timestamp).toLocaleString('ru-RU');
    return {title, description, position, time};
  }

  function renderChronicle(events, list) {
    if (!list || !Array.isArray(events)) return;
    list.replaceChildren();
    if (!events.length) { const empty = document.createElement('li'); empty.textContent = 'Здесь появится история твоих действий.'; list.append(empty); return; }
    for (const event of events.slice(-24).reverse()) {
      const description = describeEvent(event), li = document.createElement('li');
      const sequence = document.createElement('span'); sequence.className = 'seq'; sequence.textContent = `#${event.sequence}`;
      const body = document.createElement('span'); body.className = 'journal-entry';
      const title = document.createElement('b'); title.className = 'event'; title.textContent = description.title;
      const meta = document.createElement('small'); meta.className = 'meta'; meta.textContent = [description.description, description.position, description.time].filter(Boolean).join(' ');
      body.append(title, meta);
      const evidence = document.createElement('details'); evidence.className = 'journal-evidence';
      const summary = document.createElement('summary'); summary.textContent = 'Данные события';
      const code = document.createElement('code'); code.textContent = `${event.type} · ${String(event.event_hash || '').slice(0,12)}`;
      evidence.append(summary, code); body.append(evidence); li.append(sequence, body); list.append(li);
    }
  }

  function savedStatus(ok) { const node = $('save-status'); if (node) node.textContent = ok ? 'Сохранено на этом устройстве' : 'Не удалось сохранить на устройстве. Проверь доступное место и настройки Safari.'; }

  function setup() {
    try { const raw = localStorage.getItem(SAVE_KEY); if (raw) { const save = JSON.parse(raw); savedStatus(save.world_id === WORLD_ID && save.world_seed === WORLD_SEED); renderChronicle(save.chronicle_hash_chain, $('chronicle-list')); } else if ($('save-status')) $('save-status').textContent = 'Мир сохранится на этом устройстве после первого действия.'; } catch { savedStatus(false); }
    document.addEventListener('genesis:save', () => savedStatus(true));
    document.addEventListener('genesis:save-error', () => savedStatus(false));
    $('save-export')?.addEventListener('click', async () => {
      const button = $('save-export'); button.disabled = true;
      try {
        const raw = await exportText(), blob = new Blob([raw], {type: 'application/json'}), url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url; link.download = `genesis-world-${new Date().toISOString().slice(0,10)}.json`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        message('Файл мира готов. Сохрани его в «Файлы», чтобы открыть на другом устройстве.');
      } catch (error) { message(error.message || 'Не удалось скачать мир.'); }
      finally { button.disabled = false; }
    });
    $('save-import')?.addEventListener('change', async event => {
      const file = event.target.files?.[0]; if (!file) return;
      const request = ++requestNumber; staged = null; buttons(false);
      if (file.size > MAX_BYTES) { cancelImport(); message('Файл слишком большой. Максимум — 2 МБ.'); return; }
      try { const raw = await file.text(); if (request === requestNumber) await stageImportText(raw); } catch (error) { if (request === requestNumber) message(error.message || 'Не удалось прочитать файл.'); }
    });
    $('save-import-confirm')?.addEventListener('click', confirmImport);
    $('save-import-cancel')?.addEventListener('click', cancelImport);
  }

  globalThis.GENESIS_WORLD_JOURNAL = Object.freeze({version: '1.0.0', exportText, parseImport, stageImportText, confirmImport, cancelImport, renderChronicle, describeEvent});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup, {once: true}); else setup();
})();
