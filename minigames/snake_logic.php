<?php
/**
 * Шаг симуляции змейки на PHP — тот же набор правил, что и в браузере.
 */
function snake_step(array $snake, array $dir, array $food, int $gridSize): array {
    $head = ['x' => $snake[0]['x'] + $dir['x'], 'y' => $snake[0]['y'] + $dir['y']];
    if ($head['x'] < 0 || $head['y'] < 0 || $head['x'] >= $gridSize || $head['y'] >= $gridSize) {
        return ['dead' => true, 'snake' => $snake, 'food' => $food];
    }
    foreach ($snake as $seg) {
        if ($seg['x'] === $head['x'] && $seg['y'] === $head['y']) {
            return ['dead' => true, 'snake' => $snake, 'food' => $food];
        }
    }

    array_unshift($snake, $head);
    $ate = ($head['x'] === $food['x'] && $head['y'] === $food['y']);
    if (!$ate) {
        array_pop($snake);
    } else {
        $occupied = [];
        foreach ($snake as $s) { $occupied[$s['x'].','.$s['y']] = true; }
        for ($i=0; $i<128; $i++) {
            $fx = random_int(0, $gridSize-1);
            $fy = random_int(0, $gridSize-1);
            if (!isset($occupied[$fx.','.$fy])) { $food = ['x'=>$fx,'y'=>$fy]; break; }
        }
    }

    return ['dead' => false, 'ate' => $ate, 'snake' => $snake, 'food' => $food];
}
?>
