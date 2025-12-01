(function(global){
  function isHit(note, targetY, window){
    return Math.abs(note.y - targetY) <= window;
  }

  function stepNotes(notes, dt, targetY, window){
    const next = [];
    for(const note of notes){
      const ny = note.y + note.speed * dt;
      if(ny <= targetY + window + 28){
        next.push({...note, y: ny});
      }
    }
    return next;
  }

  global.PulseCpp = {isHit, stepNotes};
})(window);
