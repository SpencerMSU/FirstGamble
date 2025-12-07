(function(global){
  /**
   * Checks if a note is within the hit window.
   * @param {object} note The note to check.
   * @param {number} note.y The y-position of the note.
   * @param {number} targetY The target y-position for hitting a note.
   * @param {number} window The size of the hit window.
   * @returns {boolean} True if the note is within the hit window, false otherwise.
   */
  function isHit(note, targetY, window){
    return Math.abs(note.y - targetY) <= window;
  }

  /**
   * Advances the state of all notes by a given time step.
   * @param {Array<object>} notes A list of notes to update.
   * @param {number} dt The time step in seconds.
   * @param {number} targetY The target y-position for hitting a note.
   * @param {number} window The size of the hit window.
   * @returns {Array<object>} The updated list of notes.
   */
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
