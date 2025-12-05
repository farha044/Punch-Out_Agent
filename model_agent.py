# model_agent.py - Aggressive MCTS for Punch-Out!! with health-based behavior

import socket, math, random

HOST, PORT = "127.0.0.1", 5001
SIMULATIONS_PER_FRAME = 600
MAX_ROLLOUT_DEPTH = 80
C_EXPLORATION = 1.4
FRAMES_PER_STEP = 9

PUNCHES = ["PUNCH_LEFT","PUNCH_RIGHT","UPPER_LEFT","UPPER_RIGHT"]
DODGES = ["DODGE_LEFT","DODGE_RIGHT","BLOCK"]

# --------------------- NODE ---------------------
class MCTSNode:
    def __init__(self, state, parent=None, action=None):
        self.state = state.copy()
        self.parent = parent
        self.action = action
        self.children = {}
        self.untried_actions = get_legal_actions(state)
        self.visits = 0
        self.value = 0.0

    def ucb1(self):
        if self.visits == 0: return float('inf')
        return self.value/self.visits + C_EXPLORATION*math.sqrt(math.log(self.parent.visits+1)/(self.visits+1))

    def best_child(self):
        if not self.children: return None
        return max(self.children.values(), key=lambda c: c.ucb1())

    def most_visited_child(self):
        if not self.children: return None
        return max(self.children.values(), key=lambda c: c.visits)

# --------------------- STATE HELPERS ---------------------
def parse_state(csv):
    p = list(map(int, csv.strip().split(',')))
    return {
        'health': p[0],
        'opp_health': p[1],
        'opp_next_action': p[2],
        'opp_timer': p[3],
        'can_punch': p[4],
        'in_fight': p[5],
        'opp_knocked': p[6],
        'hearts_lost': p[7],
        'jab_cooldown': 0,
        'upper_cooldown': 0,
    }

def get_legal_actions(state):
    # Only NONE if fight not active or opponent is down
    if state['in_fight'] != 255 or state['opp_knocked']:
        return ['NONE']
    
    actions = []

    # Always allow punches if player is alive
    if state['health'] > 0:
        actions += PUNCHES

    # Always allow dodges
    actions += DODGES

    return actions if actions else ['NONE']


# --------------------- MODEL STEP ---------------------
def step(state, action):
    s = state.copy()
    reward = 0.0
    down = (s['hearts_lost'] > 0)

    # Initialize cooldowns if missing
    if 'jab_cooldown' not in s: s['jab_cooldown'] = 0
    if 'upper_cooldown' not in s: s['upper_cooldown'] = 0

    # Handle punches
    if action in PUNCHES and (s['health'] > 0 or down):
        if 'UPPER' in action:
            if s['upper_cooldown'] == 0:
                s['upper_cooldown'] = 20
                dmg = random.randint(20,34)
                s['opp_health'] = max(0, s['opp_health'] - dmg)
                reward += dmg*8 + 80
        else:
            if s['jab_cooldown'] == 0:
                s['jab_cooldown'] = 14
                dmg = random.randint(10,18)
                s['opp_health'] = max(0, s['opp_health'] - dmg)
                reward += dmg*4 + 10

    # Reduce cooldowns each step
    s['jab_cooldown'] = max(0, s['jab_cooldown'] - 1)
    s['upper_cooldown'] = max(0, s['upper_cooldown'] - 1)

    # Opponent attack
    s['opp_timer'] = max(0, s['opp_timer'] - FRAMES_PER_STEP)
    if s['opp_timer'] <= 0:
        dmg = random.randint(15,28)
        s['health'] = max(0, s['health'] - dmg)
        s['opp_timer'] = 35 + random.randint(0,30)
        reward -= dmg*0.5

    return s, reward

# --------------------- ROLLOUT POLICY ---------------------
def rollout_policy(state):
    legal_actions = get_legal_actions(state)
    if not legal_actions:
        return 'NONE'

    # 10-count: player is down and needs to get up
    down = (state['hearts_lost'] > 0)  # simple check for down
    if down:
        punches = [a for a in ["PUNCH_LEFT", "PUNCH_RIGHT"] if a in legal_actions]
        if punches:
            return random.choice(punches)
        else:
            return 'NONE'
    # Critical stamina: dodge only
    if state['can_punch'] <= 5:
        dodge_actions = [a for a in legal_actions if a in DODGES]
        return random.choice(dodge_actions) if dodge_actions else 'NONE'

    # Low stamina: mix, favor dodges slightly
    if state['can_punch'] <= 9:
        attack_actions = [a for a in legal_actions if a in PUNCHES]
        dodge_actions = [a for a in legal_actions if a in DODGES]
        pool = dodge_actions*2 + attack_actions  # 2:1 dodge bias
        return random.choice(pool) if pool else 'NONE'

    # Health-based aggression
    attack_actions = [a for a in legal_actions if a in PUNCHES]
    dodge_actions = [a for a in legal_actions if a in DODGES]

    if state['health'] > 70:
        uppercuts = [a for a in attack_actions if a in ["UPPER_LEFT","UPPER_RIGHT"]]
        jabs = [a for a in attack_actions if a in ["PUNCH_LEFT","PUNCH_RIGHT"]]
        if uppercuts and jabs:
            return random.choice(uppercuts + jabs)
        elif uppercuts:
            return random.choice(uppercuts)
        elif jabs:
            return random.choice(jabs)
    else:
        pool = attack_actions + dodge_actions
        return random.choice(pool) if pool else 'NONE'

    # fallback dodge
    return random.choice([a for a in legal_actions if a in DODGES]) if DODGES else 'NONE'



# --------------------- ROLLOUT ---------------------
def rollout(state):
    s = state.copy()
    total_reward = 0.0
    depth = 0
    while depth < MAX_ROLLOUT_DEPTH:
        depth += 1
        if s['opp_health'] <= 0:
            total_reward += 5000 + depth*30
            break
        action = rollout_policy(s)
        s, r = step(s, action)
        total_reward += r
    return total_reward

# --------------------- MCTS SEARCH ---------------------
def mcts_search(init_state):
    root = MCTSNode(init_state)
    for _ in range(SIMULATIONS_PER_FRAME):
        node = root
        while node.untried_actions == [] and node.children:
            node = node.best_child()
        if node.untried_actions:
            legal_expansions = [a for a in node.untried_actions if a]
            a = random.choice(legal_expansions) if legal_expansions else 'NONE'
            node.untried_actions.remove(a)
            child_s, _ = step(node.state, a)
            child = MCTSNode(child_s, node, a)
            node.children[a] = child
            node = child
        reward = rollout(node.state)
        while node:
            node.visits += 1
            node.value += reward
            node = node.parent
    best = root.most_visited_child()
    legal_actions = get_legal_actions(init_state)
    if not legal_actions:
        return 'NONE'
    return best.action if best and best.action in legal_actions else random.choice(legal_actions)

# --------------------- SERVER ---------------------
def run_server():
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    sock.bind((HOST,PORT))
    sock.listen(1)
    print(f"Aggressive MCTS Agent Ready | {SIMULATIONS_PER_FRAME} sims/frame | {MAX_ROLLOUT_DEPTH} depth")
    conn, addr = sock.accept()
    print(f"Connected: {addr}")

    frame_count = 0
    while True:
        try:
            data = conn.recv(1024)
            if not data: break
            csv = data.decode().strip()
            if len(csv.split(',')) != 8:
                conn.send("NONE\n".encode())
                continue
            state = parse_state(csv)
            frame_count += 1

            legal_actions = get_legal_actions(state)
            if not legal_actions or state['opp_health'] <= 0 or state['opp_knocked'] or state['in_fight'] != 255:
                action = 'NONE'
            else:
                action = mcts_search(state)

            if frame_count % 10 == 0:
                print(f"F{frame_count:4d} | {action:12s} | HP:{state['health']:2d}/{state['opp_health']:2d} | T:{state['opp_timer']:3d} | P:{state['can_punch']} | H:{state['hearts_lost']:3d}")
            conn.send((action+"\n").encode())
        except Exception as e:
            print(f"Error: {e}")
            conn.send("NONE\n".encode())

if __name__ == "__main__":
    run_server()
