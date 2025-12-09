import random
import time
from typing import List, Dict, Optional, Tuple

# Card Ranks: 2-9, 10=T, J, Q, K, A
# Suits: H (Hearts), D (Diamonds), C (Clubs), S (Spades)

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS = ['H', 'D', 'C', 'S']

def rank_value(r: str) -> int:
    return RANKS.index(r)

class Card:
    def __init__(self, rank: str, suit: str):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def to_dict(self):
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_str(s: str):
        if len(s) < 2: return None
        return Card(s[:-1], s[-1])

class Deck:
    def __init__(self, size: int = 36):
        self.cards = []
        start_idx = 0
        if size == 24: start_idx = RANKS.index('9') # 9, T, J, Q, K, A
        elif size == 36: start_idx = RANKS.index('6') # 6..A
        elif size == 52: start_idx = 0 # 2..A

        chosen_ranks = RANKS[start_idx:]
        for s in SUITS:
            for r in chosen_ranks:
                self.cards.append(Card(r, s))
        random.shuffle(self.cards)

    def draw(self) -> Optional[Card]:
        if not self.cards: return None
        return self.cards.pop()

    def set_trump(self) -> Card:
        if not self.cards: return Card('2', 'H') # Fallback?
        # In Durak, the last card is the trump and stays at the bottom
        # Actually in physical game, you draw one, put it face up under the deck.
        # Logic: Move last card to a "trump" property, but it is effectively the last card in list.
        # We just peek it.
        return self.cards[0]

class Player:
    def __init__(self, uid: int, name: str):
        self.uid = uid
        self.name = name
        self.hand: List[Card] = []
        self.is_ready = False
        self.is_out = False # Finished game
        self.last_active = time.time()

class DurakGame:
    def __init__(self, room_id: str, settings: Dict):
        self.room_id = room_id
        self.settings = settings # size: 24/36/52, mode: 'podkidnoy'/'perevodnoy'
        self.players: List[Player] = []
        self.deck: Deck = None
        self.trump_card: Card = None
        self.trump_suit: str = None

        self.table: List[Tuple[Card, Optional[Card]]] = [] # List of (AttackCard, DefendCard|None)

        self.attacker_idx: int = 0
        self.defender_idx: int = 1

        self.state = "waiting" # waiting, playing, finished
        self.turn_state = "attack" # attack, defend
        self.pass_count = 0 # how many attackers passed
        self.winner_order = []
        self.created_at = time.time()

    def add_player(self, uid: int, name: str) -> bool:
        if self.state != "waiting": return False
        if len(self.players) >= 4: return False
        if any(p.uid == uid for p in self.players): return False
        self.players.append(Player(uid, name))
        return True

    def remove_player(self, uid: int):
        self.players = [p for p in self.players if p.uid != uid]
        if self.state == "playing" and len(self.players) < 2:
            self.state = "aborted"

    def set_ready(self, uid: int, ready: bool):
        for p in self.players:
            if p.uid == uid:
                p.is_ready = ready
                p.last_active = time.time()

    def start_game(self):
        if len(self.players) < 2: return
        self.deck = Deck(size=self.settings.get("size", 36))

        # Deal 6 cards
        for _ in range(6):
            for p in self.players:
                c = self.deck.draw()
                if c: p.hand.append(c)

        if self.deck.cards:
            self.trump_card = self.deck.cards[0] # Bottom card
            self.trump_suit = self.trump_card.suit
        else:
            self.trump_suit = 'H' # rare edge case

        # Determine first attacker (lowest trump)
        min_trump = 100
        starter_idx = 0
        for i, p in enumerate(self.players):
            for c in p.hand:
                if c.suit == self.trump_suit:
                    val = rank_value(c.rank)
                    if val < min_trump:
                        min_trump = val
                        starter_idx = i

        self.attacker_idx = starter_idx
        self.defender_idx = (starter_idx + 1) % len(self.players)
        self.state = "playing"
        self.turn_state = "attack"
        self.table = []

    def get_snapshot(self, for_uid: int):
        # Return state visible to user
        pl_data = []
        for i, p in enumerate(self.players):
            is_me = (p.uid == for_uid)
            pl_data.append({
                "uid": p.uid,
                "name": p.name,
                "cards_count": len(p.hand),
                "is_attacker": (i == self.attacker_idx),
                "is_defender": (i == self.defender_idx),
                "is_out": p.is_out,
                "ready": p.is_ready,
                # Show cards only if me
                "hand": [c.to_dict() for c in p.hand] if is_me else []
            })

        return {
            "room_id": self.room_id,
            "state": self.state,
            "trump_suit": self.trump_suit,
            "trump_card": self.trump_card.to_dict() if self.trump_card else None,
            "deck_count": len(self.deck.cards) if self.deck else 0,
            "table": [{"attack": pair[0].to_dict(), "defend": pair[1].to_dict() if pair[1] else None} for pair in self.table],
            "players": pl_data,
            "turn_state": self.turn_state
        }

    def _next_turn(self, defender_picked: bool):
        # 1. Refill hands
        # Attacker first, then others, then defender
        # Order: attacker, others clockwise, defender

        active_players = [p for p in self.players if not p.is_out]
        if not active_players:
            self.state = "finished"
            return

        # Simple refill loop starting from attacker
        # We need mapping from game index to active list?
        # Just iterate all players starting from attacker_idx
        n = len(self.players)
        indices = []
        curr = self.attacker_idx
        for _ in range(n):
            indices.append(curr)
            curr = (curr + 1) % n

        for idx in indices:
            p = self.players[idx]
            if p.is_out: continue
            while len(p.hand) < 6 and self.deck.cards:
                c = self.deck.draw()
                p.hand.append(c)

        # 2. Check winners (empty hand and empty deck)
        # Mark players as out
        for p in self.players:
            if not p.is_out and len(p.hand) == 0 and not self.deck.cards:
                p.is_out = True
                self.winner_order.append(p.uid)

        # 3. Determine next attacker/defender
        active = [i for i, p in enumerate(self.players) if not p.is_out]

        if len(active) < 2:
            self.state = "finished"
            return

        if defender_picked:
            # Defender skips turn as attacker.
            # Next attacker is the player after defender.
            # Need to find next active player after defender_idx
            # Defender idx might be out now?

            # Find closest active player after defender
            next_att = (self.defender_idx + 1) % n
            while next_att not in active:
                next_att = (next_att + 1) % n
            self.attacker_idx = next_att
        else:
            # Defender beat everything, becomes attacker
            if self.defender_idx in active:
                self.attacker_idx = self.defender_idx
            else:
                 # defender went out, next player is attacker
                next_att = (self.defender_idx + 1) % n
                while next_att not in active:
                    next_att = (next_att + 1) % n
                self.attacker_idx = next_att

        # Find new defender (next active after new attacker)
        next_def = (self.attacker_idx + 1) % n
        while next_def not in active or next_def == self.attacker_idx:
            next_def = (next_def + 1) % n
        self.defender_idx = next_def

        self.table = []
        self.turn_state = "attack"
        self.pass_count = 0


    def action_attack(self, uid: int, card_dict: Dict):
        # Only attacker (or others if table not empty) can throw
        # For simplicity MVP: only designated attacker or any non-defender if table not empty
        p_idx = -1
        for i, p in enumerate(self.players):
            if p.uid == uid: p_idx = i; break
        if p_idx == -1: return

        if p_idx == self.defender_idx: return # Defender can't attack (unless transfer, handled separately)

        # Check if it's the main attacker or generic throw-in
        if not self.table and p_idx != self.attacker_idx: return # Only main attacker starts

        card = Card(card_dict['rank'], card_dict['suit'])
        # Verify card in hand
        p = self.players[p_idx]
        found = False
        for c in p.hand:
            if c.rank == card.rank and c.suit == card.suit:
                found = True; break
        if not found: return

        # Verify rank match if table not empty
        if self.table:
            ranks_on_table = {pair[0].rank for pair in self.table} | {pair[1].rank for pair in self.table if pair[1]}
            if card.rank not in ranks_on_table: return

        if len(self.table) >= 6: return # Max 6 cards usually

        # Check if defender has enough cards (cannot throw more than defender holds)
        defender = self.players[self.defender_idx]
        unbeaten_count = sum(1 for pair in self.table if pair[1] is None)
        if unbeaten_count + 1 > len(defender.hand): return

        # Execute
        # Remove from hand
        p.hand = [c for c in p.hand if not (c.rank == card.rank and c.suit == card.suit)]
        self.table.append((card, None))
        self.turn_state = "defend"
        self.pass_count = 0 # Reset pass count on new attack

    def action_defend(self, uid: int, attack_card_idx: int, card_dict: Dict):
        if self.players[self.defender_idx].uid != uid: return

        if attack_card_idx < 0 or attack_card_idx >= len(self.table): return
        pair = self.table[attack_card_idx]
        if pair[1] is not None: return # Already beaten

        atk_card = pair[0]
        def_card = Card(card_dict['rank'], card_dict['suit'])

        # Verify in hand
        p = self.players[self.defender_idx]
        found = False
        for c in p.hand:
            if c.rank == def_card.rank and c.suit == def_card.suit:
                found = True; break
        if not found: return

        # Verify beats
        beats = False
        if atk_card.suit == def_card.suit:
            if rank_value(def_card.rank) > rank_value(atk_card.rank):
                beats = True
        elif def_card.suit == self.trump_suit:
            beats = True

        if not beats: return

        # Execute
        p.hand = [c for c in p.hand if not (c.rank == def_card.rank and c.suit == def_card.suit)]
        self.table[attack_card_idx] = (atk_card, def_card)

    def action_take(self, uid: int):
        if self.players[self.defender_idx].uid != uid: return

        # Defender takes all cards
        p = self.players[self.defender_idx]
        for pair in self.table:
            p.hand.append(pair[0])
            if pair[1]: p.hand.append(pair[1])

        self._next_turn(defender_picked=True)

    def action_pass(self, uid: int):
        # Attacker says "done"
        if uid == self.players[self.defender_idx].uid: return

        # Only counts if table is fully beaten? Or if attackers have nothing more to add
        # In simple UI: attackers press "Pass/Done".
        # If all active attackers pass, and table is beaten -> turn ends, cards discarded.

        # Check if table has unbeaten cards
        unbeaten = any(pair[1] is None for pair in self.table)
        if unbeaten: return # Cannot pass if defender hasn't beaten everything yet

        # For simplicity: if main attacker passes, we assume turn end (unless we want strict multiplayer 'add' phase)
        # Let's simple implementation: Main attacker passes -> turn ends.
        if uid == self.players[self.attacker_idx].uid:
            self._next_turn(defender_picked=False)

    def action_transfer(self, uid: int, card_dict: Dict):
        # Perevodnoy logic (Transfer)
        if self.settings.get("mode") != "perevodnoy": return
        if self.players[self.defender_idx].uid != uid: return

        # Can only transfer if no cards are beaten yet
        if any(pair[1] is not None for pair in self.table): return

        card = Card(card_dict['rank'], card_dict['suit'])

        # Rank must match existing attack cards
        if not self.table: return
        if self.table[0][0].rank != card.rank: return

        # Verify hand
        p = self.players[self.defender_idx]
        if not any(c.rank == card.rank and c.suit == card.suit for c in p.hand): return

        # Check if next player has enough cards to defend (current table + 1)
        next_p_idx = (self.defender_idx + 1) % len(self.players)
        # Skip finished?
        # ... logic complexity ...
        # Assume active.
        next_p = self.players[next_p_idx]
        if len(next_p.hand) < len(self.table) + 1: return # Can't transfer

        # Execute
        p.hand = [c for c in p.hand if not (c.rank == card.rank and c.suit == card.suit)]
        self.table.append((card, None))

        # Rotate roles
        self.attacker_idx = self.defender_idx
        self.defender_idx = next_p_idx
