<?php
function is_hit(array $note, float $targetY, float $window): bool {
    return abs($note['y'] - $targetY) <= $window;
}

function step_notes(array $notes, float $dt, float $targetY, float $window): array {
    $result = [];
    foreach ($notes as $n) {
        $n['y'] += $n['speed'] * $dt;
        if ($n['y'] <= $targetY + $window + 28) {
            $result[] = $n;
        }
    }
    return $result;
}

// $notes = [['lane'=>1,'y'=>-30,'speed'=>185]];
// $notes = step_notes($notes, 0.016, 320.0, 42.0);
// if (is_hit($notes[0], 320.0, 42.0)) { /* award point */ }
?>
