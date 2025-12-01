<?php
/**
 * Мини-симуляция грави-ритма: движение объектов и проверка столкновений.
 */
function gravirun_step(array $state, float $dt, int $laneCount = 4): array {
    $lanes = range(0, $laneCount-1);
    $state['spawnTimer'] = ($state['spawnTimer'] ?? 0) + $dt;
    $state['spawnDelay'] = $state['spawnDelay'] ?? 0.95;
    if ($state['spawnTimer'] >= $state['spawnDelay']) {
        $state['spawnTimer'] = 0;
        $state['spawnDelay'] = max(0.45, $state['spawnDelay'] * 0.985);
        $roll = mt_rand() / mt_getrandmax();
        $type = $roll < 0.68 ? 'crystal' : ($roll < 0.87 ? 'spike' : 'boost');
        $state['objects'][] = ['lane' => $lanes[array_rand($lanes)], 'y' => -30.0, 'speed' => 170.0, 'type' => $type];
    }

    $state['objects'] = array_map(function($o) use ($dt){
        $o['y'] += $o['speed'] * $dt;
        return $o;
    }, $state['objects'] ?? []);

    $playerLane = $state['playerLane'] ?? 1;
    $playerY = 0.8;
    $score = $state['score'] ?? 0;
    $lives = $state['lives'] ?? 3;
    $boostTimer = $state['boostTimer'] ?? 0.0;

    foreach ($state['objects'] as $idx => $obj) {
        if ($obj['lane'] !== $playerLane) continue;
        if (abs($obj['y'] - $playerY) <= 0.08) {
            if ($obj['type'] === 'crystal') {
                $score += ($boostTimer > 0) ? 2 : 1;
                unset($state['objects'][$idx]);
            } elseif ($obj['type'] === 'spike') {
                if ($boostTimer > 0) {
                    unset($state['objects'][$idx]);
                } else {
                    $lives -= 1;
                    unset($state['objects'][$idx]);
                }
            } else {
                $boostTimer = 1.5;
                unset($state['objects'][$idx]);
            }
        }
    }

    $state['objects'] = array_values(array_filter($state['objects'], fn($o) => $o['y'] < 1.4));
    $state['score'] = $score;
    $state['lives'] = $lives;
    $state['boostTimer'] = max(0.0, $boostTimer - $dt);

    return $state;
}
?>
