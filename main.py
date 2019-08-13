from copy import deepcopy
from functools import partial
from itertools import product
from random import Random
from typing import List


class House(str):
    def __deepcopy__(self, memo):
        return self


Dis = "Dis"
Shadows = "Shadows"
Brobnar = "Brobnar"
Untamed = "Untamed"


class Card:
    house = None

    def play(self, state) -> None:
        """On play trigger"""
        pass

    def __deepcopy__(self, memo):
        return self

    def __repr__(self) -> str:
        return self.__class__.__name__


class CreatureCard(Card):
    power = None
    armor = 0
    elusive = False
    action = None

    def play(self, state, creature):
        """Play hook"""
        pass

    def reap(self, state, creature):
        """Reap hook"""
        pass

    def destroyed(self, state, creature):
        """Destroyed hook"""
        pass


def steal(state, amount) -> None:
    a = min(amount, state.opponent().aember)
    state.opponent().aember -= a
    state.active.aember += a
    

# SHADOWS
class Silvertooth(CreatureCard):
    house = Shadows
    power = 2

    def play(self, state, creature):
        creature.ready = True  # Silvertooth enters play ready


class NoddyTheThief(CreatureCard):
    house = Shadows
    power = 2
    elusive = True
    action = partial(steal, amount=1)

class Urchin(CreatureCard):
    house = Shadows
    power = 1
    elusive = True
    def play(self, state, creature):
        steal(state, amount=1)

# UNTAMED
class DewFaerie(CreatureCard):
    house = Untamed
    power = 2
    elusive = True
    
    def reap(self, state, creature):
        state.active.aember += 1

class Player:
    def __init__(self, random: Random, deck: List[Card]): 
        self.aember = 0
        self.hand = []
        self.battle_line = []
        self.discard = []
        self.deck = deck
        random.shuffle(self.deck)
        self.forged = 0


class Creature:
    def __init__(self, card: Card):
        self.card = card
        self.damage_taken = 0
    
        self.ready = False
        self.elusive = card.elusive
        self.armor = card.armor
    
    def power(self) -> int:
        return self.card.power

    def can_fight(self, target) -> bool:
        return True

    def play(self, state) -> None:
        """Play hook"""
        self.card.play(state, creature=self)

    def reap(self, state) -> None:
        """Reap hook"""
        self.card.reap(state, creature=self)


class State:
    def __init__(self, deck1, deck2):
        self.random = Random(1337)
        self.players = (Player(self.random, deck1), Player(self.random, deck2))
        self.active = self.players[0]
        self.house = None
        self.round = 0

        # draw cards
        self.draw(self.players[0], to=7)
        self.draw(self.players[1], to=6)
    
    def cull(self) -> None:
        """Remove all destroyed creatures"""
        for player in self.players:
            to_remove = [creature for creature in player.battle_line if creature.damage_taken >= creature.power()]
            for creature in to_remove:
                player.battle_line.remove(creature)
                to_remove.destroyed(self, creature)

    def opponent(self) -> Player:
        one, other = self.players
        return other if self.active == one else one

    def draw(self, player: Player, to: int) -> None:
        while len(player.hand) < to:
            # if deck empty, shuffle discard into deck
            if not player.deck:
                player.deck = player.discard
                player.discard = []
                self.random.shuffle(player.deck)

            card = player.deck.pop()
            player.hand.append(card)

    def game_over(self) -> bool:
        return any(True for player in self.players if player.forged >= 3)

    def winner(self) -> Player:
        return next((player for player in self.players if player.forged >= 3), None)


def end_turn(state: State) -> None:
    # 1. Ready creatues
    for creature in state.active.battle_line:
        creature.ready = True
        creature.elusive = creature.card.elusive
        creature.armor = creature.card.armor

    # 2. Draw cards
    state.draw(state.active, to=6)

    # 3. Unselect house
    state.house = None

    # 4. Update active player
    state.active = state.opponent()

    # 5. Forge key, if possible
    cost = 6
    if state.active.aember >= cost:
        state.active.aember -= cost
        state.active.forged += 1


class Play:
    def __init__(self, card: Card):
        self.card = card

    def __call__(self, state: State) -> None:
        state.active.hand.remove(self.card)
        creature = Creature(self.card)
        state.active.battle_line.append(creature)
        creature.play(state)

    def __repr__(self) -> str:
        return "Play({card})".format(card=self.card)


class Reap:
    def __init__(self, creature: Creature):
        self.creature = creature
    
    def __call__(self, state: State) -> None:
        state.active.aember += 1
        self.creature.ready = False
        self.creature.reap(state)
    
    def __repr__(self) -> str:
        return "Reap({card})".format(card=self.creature.card)


class Fight:
    def __init__(self, creature: Creature, target: Creature):
        self.creature = creature
        self.target = target

    def __call__(self, state: State) -> None:
        if self.target.elusive:
            self.target.elusive = False
            return

        self.creature.damage_taken += self.target.power()
        self.target.damage_taken += self.creature.power() - self.target.armor
        self.target.armor = 0

        state.cull()

    def __repr__(self) -> str:
        return "Fight({card}, {target})".format(
            card=self.creature.card,
            target=self.target.card)


class CreatureAction:
    def __init__(self, creature: Creature):
        self.creature = creature

    def __call__(self, state: State) -> None:
        self.creature.card.action(state)
        self.creature.ready = False

    def __repr__(self) -> str:
        return "Action({card})".format(card=self.creature.card)


class SelectHouse:
    def __init__(self, house: House):
        self.house = house
    
    def __call__(self, state: State) -> None:
        state.house = self.house

    def __repr__(self) -> str:
        return "SelectHouse({house})".format(house=self.house)
    

def valid_actions(state: State):
    player = state.active
    if state.house is None:
        houses = \
            set([creature.card.house for creature in player.battle_line]) | \
            set([card.house for card in player.hand])
        return [SelectHouse(house) for house in houses]

    # play cards, reap, fight, action, discard cards, end turn
    #[Fight(creature) for creature in player.battle_line if creature.card.house == state.house] + \
    ready_creatures = [creature for creature in player.battle_line if creature.card.house == state.house and creature.ready]
    return \
        [Play(card) for card in player.hand if card.house == state.house] + \
        [Reap(creature) for creature in ready_creatures] + \
        [Fight(creature, target) for creature, target in product(ready_creatures, state.opponent().battle_line) if creature.can_fight(target)] + \
        [CreatureAction(creature) for creature in ready_creatures if creature.card.action] + \
        [end_turn]


def main():
    random = Random()
    deck1 = [Silvertooth(), NoddyTheThief(), DewFaerie(), Urchin()] * 8
    deck2 = [Silvertooth(), NoddyTheThief(), DewFaerie(), Urchin()] * 8

    # initial state
    state = State(deck1, deck2)

    while not state.game_over():
        tmp = valid_actions(state)
        #print(len(tmp))
        action = random.choice(tmp)
        print(action)

        # apply state
        state = deepcopy(state)
        action(state)

main()
