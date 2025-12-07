(function(global){
  /**
   * Converts a point object to a string key.
   * @param {object} p The point object.
   * @param {number} p.x The x-coordinate.
   * @param {number} p.y The y-coordinate.
   * @returns {string} The string key.
   */
  function toKey(p){ return `${p.x},${p.y}`; }

  /**
   * Places a new piece of food on the grid.
   * @param {Array<object>} snake The current state of the snake.
   * @param {number} gridSize The size of the game grid.
   * @returns {object} The coordinates of the new food.
   */
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

  /**
   * Advances the state of the Snake game by one step.
   * @param {Array<object>} snake The current state of the snake.
   * @param {object} dir The direction in which the snake is moving.
   * @param {object} food The current position of the food.
   * @param {number} gridSize The size of the game grid.
   * @returns {object} An object containing the new state of the game.
   */
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
