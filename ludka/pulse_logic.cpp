#include <vector>
#include <cmath>

struct Note {
    int lane;      // 0..2
    double y;      // current position
    double speed;  // px per second
};

bool isHit(const Note& n, double targetY, double window){
    return std::abs(n.y - targetY) <= window;
}

// Advance all notes by dt seconds and remove those that flew away.
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
