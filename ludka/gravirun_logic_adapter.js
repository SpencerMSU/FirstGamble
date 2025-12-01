(function(global){
  const DEFAULT_BASE_HEIGHT = 420;
  function makeState(){
    return {objects:[], playerLane:1, spawnTimer:0, spawnDelay:0.95, score:0, lives:3, boostTimer:0};
  }

  function gravirunStepCpp(state, dt, options={}){
    const laneCount = options.laneCount ?? 4;
    const baseHeight = options.boardHeight || DEFAULT_BASE_HEIGHT;
    const pxToUnit = 1 / baseHeight;
    const spawnY = -30 * pxToUnit;
    const speed = 170 * pxToUnit;
    const dropLimit = 1.4;
    const playerY = 0.8;
    const hitWindow = 0.08;

    const events = [];
    state.spawnTimer += dt;
    if(state.spawnTimer >= state.spawnDelay){
      state.spawnTimer = 0;
      state.spawnDelay = Math.max(0.45, state.spawnDelay * 0.985);
      const r = Math.random();
      const type = r < 0.68 ? 'c' : (r < 0.87 ? 's' : 'b');
      state.objects.push({lane: Math.floor(Math.random()*laneCount), y: spawnY, speed, type});
    }

    state.objects.forEach(o => { o.y += o.speed * dt; });

    state.objects.forEach(o => {
      if(o.lane !== state.playerLane) return;
      if(Math.abs(o.y - playerY) <= hitWindow){
        if(o.type === 'c'){
          const points = state.boostTimer > 0 ? 2 : 1;
          state.score += points;
          events.push({type:'crystal', points});
          o.type = 'x';
        }else if(o.type === 's'){
          if(state.boostTimer <= 0){
            state.lives -= 1;
            events.push({type:'spike', lifeLost:true});
          }else{
            events.push({type:'spike', lifeLost:false});
          }
          o.type = 'x';
        }else if(o.type === 'b'){
          state.boostTimer = 1.5;
          events.push({type:'boost'});
          o.type = 'x';
        }
      }
    });

    state.objects = state.objects.filter(o => o.type !== 'x' && o.y < dropLimit);
    state.boostTimer = Math.max(0, state.boostTimer - dt);

    return {state, events};
  }

  global.GravirunCpp = {makeState, gravirunStepCpp};
})(window);
