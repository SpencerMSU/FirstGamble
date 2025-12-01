#include <vector>
#include <random>
#include <algorithm>

struct Object{int lane; double y; double speed; char type;};
struct State{
    std::vector<Object> objects; int playerLane=1; double spawnTimer=0; double spawnDelay=0.95;
    int score=0; int lives=3; double boostTimer=0.0;
};

static std::mt19937 rng{std::random_device{}()};

State gravirun_step(State state, double dt, int laneCount=4){
    state.spawnTimer += dt;
    if(state.spawnTimer >= state.spawnDelay){
        state.spawnTimer = 0;
        state.spawnDelay = std::max(0.45, state.spawnDelay * 0.985);
        std::uniform_real_distribution<double> roll(0.0,1.0);
        double r = roll(rng);
        char t = r < 0.68 ? 'c' : (r < 0.87 ? 's' : 'b');
        std::uniform_int_distribution<int> laneDist(0,laneCount-1);
        state.objects.push_back({laneDist(rng), -30.0, 170.0, t});
    }

    for(auto &o : state.objects){ o.y += o.speed * dt; }

    double playerY = 0.8;
    for(auto &o : state.objects){
        if(o.lane != state.playerLane) continue;
        if(std::abs(o.y - playerY) <= 0.08){
            if(o.type == 'c'){
                state.score += (state.boostTimer > 0) ? 2 : 1;
                o.type = 'x';
            }else if(o.type == 's'){
                if(state.boostTimer > 0){
                    o.type = 'x';
                }else{
                    state.lives -= 1;
                    o.type = 'x';
                }
            }else if(o.type == 'b'){
                state.boostTimer = 1.5;
                o.type = 'x';
            }
        }
    }

    state.objects.erase(std::remove_if(state.objects.begin(), state.objects.end(), [](const Object &o){
        return o.type=='x' || o.y >= 1.4;
    }), state.objects.end());

    state.boostTimer = std::max(0.0, state.boostTimer - dt);
    return state;
}

// Пример: State s; s = gravirun_step(s, 0.016);
