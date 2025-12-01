(function(global){
  function toKey(p){ return `${p.x},${p.y}`; }

  function placeFood(snake, gridSize){
    const occupied = new Set(snake.map(toKey));
    for(let i=0;i<128;i++){
      const fx = Math.floor(Math.random()*gridSize);
      const fy = Math.floor(Math.random()*gridSize);
      const key = `${fx},${fy}`;
      if(!occupied.has(key)) return {x:fx,y:fy};
    }
    return snake[0] ? {...snake[0]} : {x:0,y:0};
  }

  function snakeStepCpp(snake, dir, food, gridSize){
    const head = {x:snake[0].x + dir.x, y:snake[0].y + dir.y};
    if(head.x < 0 || head.y < 0 || head.x >= gridSize || head.y >= gridSize){
      return {dead:true, ate:false, snake, food};
    }
    for(const seg of snake){
      if(seg.x === head.x && seg.y === head.y){
        return {dead:true, ate:false, snake, food};
      }
    }

    const next = [head, ...snake];
    let ate = false;
    let nextFood = food;
    if(head.x === food.x && head.y === food.y){
      ate = true;
      nextFood = placeFood(next, gridSize);
    }else{
      next.pop();
    }
    return {dead:false, ate, snake:next, food:nextFood};
  }

  global.SnakeCpp = {snakeStepCpp, placeFood};
})(window);
