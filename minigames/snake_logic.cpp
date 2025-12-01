#include <vector>
#include <unordered_set>
#include <string>
#include <random>

struct Point{int x;int y;};
struct StepResult{bool dead;bool ate;std::vector<Point> snake;Point food;};

static std::mt19937 rng{std::random_device{}()};

StepResult snake_step(std::vector<Point> snake, Point dir, Point food, int gridSize){
    Point head{snake[0].x + dir.x, snake[0].y + dir.y};
    if(head.x < 0 || head.y < 0 || head.x >= gridSize || head.y >= gridSize){
        return {true,false,snake,food};
    }
    for(const auto &seg: snake){
        if(seg.x == head.x && seg.y == head.y){
            return {true,false,snake,food};
        }
    }

    snake.insert(snake.begin(), head);
    bool ate = (head.x == food.x && head.y == food.y);
    if(!ate){
        snake.pop_back();
    }else{
        std::unordered_set<std::string> occupied;
        occupied.reserve(snake.size()*2);
        for(const auto &s: snake){ occupied.insert(std::to_string(s.x)+","+std::to_string(s.y)); }
        std::uniform_int_distribution<int> dist(0, gridSize-1);
        for(int i=0;i<128;i++){
            int fx = dist(rng), fy = dist(rng);
            std::string key = std::to_string(fx)+","+std::to_string(fy);
            if(!occupied.count(key)){ food = {fx,fy}; break; }
        }
    }
    return {false, ate, snake, food};
}

// Пример использования:
// auto res = snake_step({{10,10}}, {1,0}, {5,5}, 20);
