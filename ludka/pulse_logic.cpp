#include <vector>
#include <cmath>

/**
 * @brief Represents a note in the Pulse game.
 */
struct Note {
    int lane;      /**< The lane of the note (0-2). */
    double y;      /**< The current y-position of the note. */
    double speed;  /**< The speed of the note in pixels per second. */
};

/**
 * @brief Checks if a note is within the hit window.
 * @param n The note to check.
 * @param targetY The target y-position for hitting a note.
 * @param window The size of the hit window.
 * @return True if the note is within the hit window, false otherwise.
 */
bool isHit(const Note& n, double targetY, double window){
    return std::abs(n.y - targetY) <= window;
}

/**
 * @brief Advances the state of all notes by a given time step.
 *
 * This function updates the position of each note based on its speed and the
 * time step. Notes that have moved past the target area are removed.
 *
 * @param notes A vector of notes to update.
 * @param dt The time step in seconds.
 * @param targetY The target y-position for hitting a note.
 * @param window The size of the hit window.
 */
void step(std::vector<Note>& notes, double dt, double targetY, double window){
    auto it = notes.begin();
    while(it != notes.end()){
        it->y += it->speed * dt;
        if(it->y > targetY + window + 28){
            it = notes.erase(it);
        }else{
            ++it;
        }
    }
}

// Example usage:
//   std::vector<Note> notes = {{0,-30,190}};
//   step(notes, 0.016, 320.0, 42.0);
//   if(isHit(notes.front(), 320.0, 42.0)) { /* award point */ }
