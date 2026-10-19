(() => {
  'use strict';

  // These descriptions use execution receipts and saved world data only. They
  // never infer a successful action from the player's requested text.
  const BIOMES = Object.freeze({meadow:'луг',forest:'лес',steppe:'степь',shore:'берег',water:'вода',highland:'возвышенность',void:'пустошь'});
  const OBJECTS = Object.freeze({lighthouse:'маяк',castle:'замок',bridge:'мост',tower:'башня',house:'дом',wall:'стена',portal:'портал',tree:'дерево',statue:'статуя',road:'дорога',generic_structure:'постройка',generic_entity:'существо',TREE:'дерево',ROCK:'камень',CRYSTAL:'кристалл',RUIN:'руины',OBELISK:'обелиск',FIRST_FIRE:'первый костёр',PLAYER_MARK:'метка',RAISE_HILL:'холм',LOWER_GROUND:'углубление'});
  const CAMERA = Object.freeze({FIRST_PERSON:'от первого лица',THIRD_PERSON:'от третьего лица',ISOMETRIC:'изометрия'});
  const DIRECTIONS = Object.freeze({N:'на север',NE:'на северо-восток',E:'на восток',SE:'на юго-восток',S:'на юг',SW:'на юго-запад',W:'на запад',NW:'на северо-запад',FORWARD:'вперёд',BACKWARD:'назад'});
  const inspectSuggestion = () => ({label:'Осмотреться',text:'осмотри место'});
  const buildSuggestion = () => ({label:'Создать маяк',text:'создай маяк'});
  const numeric = value => typeof value==='number' && Number.isFinite(value);
  const format = value => numeric(value) ? String(Math.round(value*100)/100).replace('.',',') : null;
  const positionText = point => numeric(point?.x)&&numeric(point?.y) ? `x ${format(point.x)}, y ${format(point.y)}` : '';
  const objectName = object => {
    if (!object) return 'объект';
    const concept = String(object.concept||object.label||object.name||'').trim();
    const kind = object.kind||object.structure_kind||object.entity_kind||object.transform_kind||object.type;
    // Keep the player's actual name. Translate generic recipe names only.
    return OBJECTS[concept]||concept||OBJECTS[kind]||String(kind||'объект').toLowerCase().replace(/_/g,' ');
  };

  function describeFailure(reason, result={}) {
    const code=String(reason||''), description={title:'Действие не выполнено',paragraphs:[],suggestions:[inspectSuggestion()],status:'failed'};
    if (/UNRESOLVED|LOCAL_DEGRADED_NEEDS|LOCAL_COMPILER_UNAVAILABLE|LOCAL_GRAPH_FAMILY_UNSUPPORTED/.test(code)) {
      description.title='Не удалось понять команду';
      description.paragraphs.push('Попробуй одно конкретное действие: осмотреть место, пройти вперёд или создать маяк.');
      description.suggestions=[inspectSuggestion(),{label:'Шаг вперёд',text:'вперёд'},buildSuggestion()];
    } else if (/DOOR_CLOSED|BEACON_DOOR_CLOSED|DOOR_NOT_OPEN/.test(code)) {
      description.paragraphs.push('Дверь маяка закрыта. Сначала открой её.');
      description.suggestions=[{label:'Открыть дверь',text:'открой дверь'},inspectSuggestion()];
    } else if (/TOO_FAR|OUT_OF_RANGE|NOT_IN_REACH/.test(code)) {
      const range=result.distance??result.interaction?.distance;
      const distance=numeric(range)?` Сейчас до него ${format(range)} м.`:'';
      description.paragraphs.push(`Подойди ближе к объекту и повтори действие.${distance}`);
      description.suggestions=[{label:'Подойти к маяку',text:'подойди к маяку'},inspectSuggestion()];
    } else if (/TARGET_NOT_FOUND|NO_NEARBY|NO_INTERACTABLE|NO_LIGHTHOUSE|LIGHTHOUSE_NOT_FOUND|BEACON_NOT_FOUND|INTERACTION_TARGET_MISSING/.test(code)) {
      description.paragraphs.push('Подходящий объект не найден. Осмотрись или создай маяк рядом с собой.');
      description.suggestions=[inspectSuggestion(),buildSuggestion()];
    } else if (/ALREADY_OPEN/.test(code)) {
      description.title='Дверь уже открыта';
      description.paragraphs.push('Можно зажечь огонь маяка.');
      description.suggestions=[{label:'Зажечь маяк',text:'зажги маяк'},inspectSuggestion()];
    } else if (/ALREADY_LIT/.test(code)) {
      description.title='Маяк уже горит';
      description.paragraphs.push('Его огонь уже включён.');
      description.suggestions=[{label:'Погасить маяк',text:'погаси маяк'},inspectSuggestion()];
    } else if (/ALREADY_UNLIT|ALREADY_EXTINGUISHED|ALREADY_DARK/.test(code)) {
      description.title='Маяк уже погашен';
      description.suggestions=[{label:'Зажечь маяк',text:'зажги маяк'},inspectSuggestion()];
    } else if (/ACTION_BLOCKED/.test(code)) {
      description.paragraphs.push('Проход перекрыт. Подойди к двери маяка и открой её или обойди препятствие стрелками.');
      description.suggestions=[{label:'Подойти к маяку',text:'подойди к маяку'},{label:'Открыть дверь',text:'открой дверь'}];
    } else if (/AUDIO_DISABLED/.test(code)) {
      description.paragraphs.push('Звук выключен. Для звуковой части сцены включи его в настройках.');
    } else if (/JUMP_AIRBORNE_OR_REARM/.test(code)) {
      description.paragraphs.push('Дождись приземления и прыгни снова.');
    } else if (/PLAYER_TEXT_TOO_LONG/.test(code)) {
      description.paragraphs.push('Сократи команду до 4000 символов и попробуй ещё раз.');
    } else if (/GROUP_PARTIAL_FAILURE/.test(code)) {
      const made=result.materialized, requested=result.requested;
      description.title='Группа создана частично';
      description.paragraphs.push(numeric(made)&&numeric(requested)?`Создано ${made} из ${requested} объектов. Уже созданные объекты остались в мире.`:'Часть объектов создана. Подробности доступны в техническом отчёте.');
    } else {
      description.paragraphs.push('Не удалось завершить действие. Осмотрись и попробуй простую команду. Причина сохранена в техническом отчёте.');
    }
    return description;
  }

  function describeInspection(inspection) {
    const paragraphs=[],location=positionText(inspection.position),biome=BIOMES[inspection.biome]||String(inspection.biome||'');
    paragraphs.push([biome?`Ты здесь: ${biome}.`:'Осмотр завершён.',location?`Координаты: ${location}.`:''].filter(Boolean).join(' '));
    const settings=inspection.world_settings||{},conditions=[];
    if(settings.time==='NIGHT')conditions.push('Сейчас ночь');
    if(settings.time==='DAY')conditions.push('Сейчас день');
    if(numeric(settings.fog)&&settings.fog>.15)conditions.push(`туман ${Math.round(settings.fog*100)}%`);
    if(conditions.length)paragraphs.push(conditions.join(', ')+'.');
    const nearby=Array.isArray(inspection.nearby)?inspection.nearby:[];
    if(nearby.length)paragraphs.push('Поблизости: '+nearby.map(item=>{
      const distance=numeric(item.distance)?` — ${format(item.distance)} м`:'';
      const states=[];
      const interaction=item.interaction_state||item.interaction||item.state||{};
      const door=item.door_open??interaction.door_open,lit=item.beacon_lit??interaction.beacon_lit;
      if(typeof door==='boolean')states.push(door?'дверь открыта':'дверь закрыта');
      if(typeof lit==='boolean')states.push(lit?'огонь горит':'огонь погашен');
      return objectName(item)+distance+(states.length?` (${states.join(', ')})`:'');
    }).join('; ')+'.');
    else paragraphs.push('Осмотр не обнаружил объектов поблизости.');
    return {paragraphs,nearby};
  }

  function describeNode(row,node={},context={}) {
    const result=row.result||{},params=node.params||{},operation=row.operation;
    if(row.status!=='APPLIED')return describeFailure(row.reason,result);
    let title='Действие выполнено',paragraphs=[],suggestions=[inspectSuggestion()];
    if(operation==='INSPECT'&&result.inspection){
      const inspection=describeInspection(result.inspection);
      title='Ты осмотрел место';paragraphs=inspection.paragraphs;
      const beacon=inspection.nearby.find(item=>(item.kind||item.structure_kind)==='lighthouse');
      if(beacon)suggestions=[{label:'Подойти к маяку',text:'подойди к маяку'},{label:'Открыть дверь',text:'открой дверь'}];
      else suggestions=[buildSuggestion(),{label:'Шаг вперёд',text:'вперёд'}];
    } else if(operation==='GENERATE_STRUCTURE'||operation==='SPAWN_ENTITY'||operation==='RUINED_TOWER') {
      const mutation=result.mutation;
      title=operation==='SPAWN_ENTITY'?'Объект появился':'Постройка создана';
      if(mutation){paragraphs.push(`Создан объект «${objectName(mutation)}»${positionText(mutation)?` в точке ${positionText(mutation)}`:''}.`);
        if(mutation.structure_kind==='lighthouse'){
          paragraphs.push('Подойди к маяку, открой дверь и зажги огонь.');
          suggestions=[{label:'Подойти к маяку',text:'подойди к маяку'},inspectSuggestion()];
        }
      }else paragraphs.push('Мир подтвердил создание объекта.');
    } else if(operation==='MOVE') {
      const before=context.before?.player_position,after=context.after?.player_position;
      title='Ты переместился';
      const distance=numeric(result.moved)?result.moved:before&&after?Math.hypot(after.x-before.x,after.y-before.y):null;
      paragraphs.push(`Движение ${DIRECTIONS[params.direction||'FORWARD']||''}${numeric(distance)?` на ${format(distance)} м`:''} завершено.${positionText(after)?` Сейчас ты в точке ${positionText(after)}.`:''}`);
      if(result.blocked)paragraphs.push('Дальше проход перекрыт. Обойди препятствие или подойди к двери маяка.');
    } else if(operation==='APPROACH') {
      title='Ты подошёл к объекту';
      const target=result.target||result.interaction||{};
      paragraphs.push(`${objectName(target)}${numeric(result.distance)?` — ${format(result.distance)} м`:''}.${positionText(context.after?.player_position)?` Твоя позиция: ${positionText(context.after.player_position)}.`:''}`);
      suggestions=[{label:'Открыть дверь',text:'открой дверь'},inspectSuggestion()];
    } else if(operation==='INTERACT') {
      const interaction=result.interaction||result,action=interaction.action||params.action;
      if(action==='APPROACH'){
        const walking=numeric(interaction.distance)&&interaction.distance>2.5;
        const nearby=numeric(interaction.distance)&&interaction.distance<=2.5;
        title=walking?'Идёшь к маяку':nearby?'Ты у двери маяка':'Подход к маяку';
        if(result.message)paragraphs.push(String(result.message));
        else if(walking)paragraphs.push('Ты идёшь к двери маяка. Стрелки останавливают подход.');
        else if(nearby)paragraphs.push('Ты рядом с дверью маяка.');
        if(numeric(interaction.distance))paragraphs.push(`До двери: ${format(interaction.distance)} м.`);
        suggestions=nearby?[{label:'Открыть дверь',text:'открой дверь'},inspectSuggestion()]:[inspectSuggestion()];
      }
      else if(action==='OPEN_DOOR'){title='Дверь открыта';paragraphs.push('Дверь маяка открыта. Теперь можно зажечь его огонь.');suggestions=[{label:'Зажечь маяк',text:'зажги маяк'},inspectSuggestion()];}
      else if(action==='LIGHT_BEACON'){title='Маяк зажжён';paragraphs.push('Огонь маяка включён. Посмотри на его луч в мире.');suggestions=[{label:'Сделать ночь',text:'сделай ночь'},{label:'Погасить маяк',text:'погаси маяк'}];}
      else if(action==='EXTINGUISH_BEACON'){title='Маяк погашен';paragraphs.push('Огонь маяка выключен.');suggestions=[{label:'Зажечь маяк',text:'зажги маяк'},inspectSuggestion()];}
      else paragraphs.push('Взаимодействие с объектом выполнено.');
    } else if(operation==='JUMP') {
      title='Прыжок';paragraphs.push('Ты оттолкнулся от земли.');
    } else if(operation==='RETURN_TO_HEARTH') {
      title='Ты вернулся к первому костру';
      if(positionText(context.after?.player_position))paragraphs.push(`Твоя позиция: ${positionText(context.after.player_position)}.`);
    } else if(operation==='PLACE_MARK') {
      title='Метка оставлена';paragraphs.push(`Метка${params.label?` «${params.label}»`:''} сохранена${positionText(context.after?.player_position)?` в точке ${positionText(context.after.player_position)}`:''}.`);
    } else if(operation==='SET_ATMOSPHERE') {
      title='Атмосфера изменилась';
      const settings=result.world_settings||context.after?.world_settings||{},parts=[];
      if(settings.time==='NIGHT')parts.push('Наступила ночь');
      if(settings.time==='DAY')parts.push('Сейчас день');
      if(numeric(settings.fog))parts.push(`туман ${Math.round(settings.fog*100)}%`);
      const weather={CLEAR:'ясная погода',RAIN:'дождь',SNOW:'снег',STORM:'гроза'}[settings.weather];
      if(weather)parts.push(weather);
      if(parts.length)paragraphs.push(parts.join(', ')+'.');
    } else if(operation==='SET_CAMERA') {
      title='Камера переключена';
      const camera=CAMERA[context.presentation?.camera_mode||params.camera];
      if(camera)paragraphs.push(`Режим: ${camera}.`);
    } else if(operation==='SET_CAMERA_DISTANCE') {
      title='Расстояние камеры изменено';
      const distance=context.presentation?.camera_distance??params.distance;
      if(numeric(distance))paragraphs.push(`Камера: ${format(distance)} м.`);
    } else if(operation==='SET_MIRROR') {
      title='Стиль мира изменён';
      const style=context.presentation?.mirror_profile||params.mirror;
      if(style)paragraphs.push(`Выбран стиль «${style}».`);
    } else if(operation==='WORLD_TRANSFORM') {
      const mutation=result.mutation;
      title=(mutation?.transform_kind||params.transform_kind)==='LOWER_GROUND'?'Земля опущена':'Холм поднят';
      if(positionText(mutation))paragraphs.push(`Место изменения: ${positionText(mutation)}.`);
    } else if(operation==='SPAWN_GROUP') {
      title='Группа объектов создана';
      if(numeric(result.count))paragraphs.push(`Создано объектов: ${result.count}.`);
    } else if(operation==='RESOLVE_MATERIAL') {
      title='Материал подготовлен';
    } else if(operation==='AUDIO_CUE') {
      title='Звуковая часть выполнена';
    } else if(operation==='SPATIAL_RELATION') {
      title='Расположение объектов проверено';
    }
    return {title,paragraphs,suggestions,status:'applied'};
  }

  function describeReceipt(receipt,context={}) {
    const rows=Array.isArray(receipt?.node_receipts)?receipt.node_receipts:[],nodes=new Map((context.graph?.nodes||[]).map(node=>[node.id,node]));
    const applied=rows.filter(row=>row.status==='APPLIED'),failed=rows.filter(row=>row.status==='FAILED'),skipped=rows.filter(row=>String(row.status).startsWith('SKIPPED'));
    if(!applied.length&&failed.length===1&&!skipped.length)return describeFailure(failed[0].reason,failed[0].result||{});
    if(rows.length===1&&applied.length===1)return describeNode(applied[0],nodes.get(applied[0].node_id),context);
    const descriptions=applied.map(row=>describeNode(row,nodes.get(row.node_id),context));
    const paragraphs=descriptions.flatMap(description=>description.paragraphs.length?description.paragraphs:[description.title+'.']);
    if(failed.length||skipped.length){
      paragraphs.unshift(`Выполнено действий: ${applied.length} из ${rows.length}. Не выполнено: ${failed.length}; пропущено из-за зависимостей: ${skipped.length}. Выполненные действия не отменены.`);
      for(const row of failed){const failure=describeFailure(row.reason,row.result||{});paragraphs.push(...failure.paragraphs);}
    }else if(rows.length>1)paragraphs.unshift(`Выполнено действий: ${applied.length} из ${rows.length}.`);
    const main=descriptions.find(description=>description.suggestions.some(suggestion=>suggestion.text==='подойди к маяку'))||descriptions.at(-1);
    return {title:!applied.length?'Команда не выполнена':failed.length||skipped.length?'Выполнена часть команды':'Команда выполнена',paragraphs,suggestions:main?.suggestions||[inspectSuggestion()],status:!applied.length?'failed':failed.length||skipped.length?'partial':'applied'};
  }

  function describeChronicle(event) {
    const data=event?.data||{},type=event?.type;
    if(type==='STRUCTURE_MATERIALIZED')return `Создан объект «${objectName(data)}»${positionText(data)?` · ${positionText(data)}`:''}`;
    if(type==='ENTITY_SPAWNED')return `Добавлен объект «${objectName(data)}»${positionText(data)?` · ${positionText(data)}`:''}`;
    if(type==='TEXT_MOVE')return `Движение ${DIRECTIONS[data.direction]||''}${numeric(data.steps)?` · ${data.steps} м`:''}`;
    if(type==='RETURN_TO_HEARTH')return 'Возвращение к первому костру';
    if(type==='PLAYER_MARK')return `Оставлена метка${data.label?` «${data.label}»`:''}`;
    if(type==='WORLD_TRANSFORMED')return data.kind==='LOWER_GROUND'?'Земля опущена':'Холм поднят';
    if(type==='ATMOSPHERE_CHANGED')return `Изменена атмосфера${data.time==='NIGHT'?' · ночь':data.time==='DAY'?' · день':''}`;
    if(type==='LIGHTHOUSE_APPROACHED')return 'Ты подошёл к маяку';
    if(type==='LIGHTHOUSE_DOOR_OPENED')return 'Открыта дверь маяка';
    if(type==='BEACON_LIT')return 'Зажжён маяк';
    if(type==='BEACON_EXTINGUISHED')return 'Погашен маяк';
    const action=data.action;
    if(action==='OPEN_DOOR')return 'Открыта дверь маяка';
    if(action==='LIGHT_BEACON')return 'Зажжён маяк';
    if(action==='EXTINGUISH_BEACON')return 'Погашен маяк';
    return String(type||'Событие мира').replace(/_/g,' ');
  }

  globalThis.GENESIS_PLAYER_FEEDBACK=Object.freeze({version:'1.0.0',describeReceipt,describeFailure,describeNode,describeChronicle,objectName,positionText});
})();
