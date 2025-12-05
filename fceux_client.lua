-- fceux_client.lua
-- Model-based MCTS client for Mike Tyson's Punch-Out!!
-- Works with model_agent.py

local ENV = dofile("env.lua")

package.path = ENV.PATH
package.cpath = ENV.COREPATH

local socket = require("socket")
local client = assert(socket.tcp())
client:connect("127.0.0.1", 5001)
client:settimeout(0) -- non-blocking

print("Connected to Python MCTS agent.")

-- ===================== ACTIONS =====================
local ACTIONS = {
    NONE        = {},
    DODGE_LEFT  = {left=true},
    DODGE_RIGHT = {right=true},
    BLOCK       = {down=true},
    PUNCH_LEFT  = {B=true},
    PUNCH_RIGHT = {A=true},
    UPPER_LEFT  = {up=true, B=true},
    UPPER_RIGHT = {up=true, A=true},
}

-- ===================== MEMORY ADDRESSES =====================
local ADDR = {
    health          = 0x0397,
    opp_health      = 0x0399,
    opp_next_action = 0x003A,
    opp_timer       = 0x0039,
    can_punch       = 0x00BC,
    in_fight        = 0x0004,
    opp_knocked     = 0x0005,
    hearts_lost     = 0x0393,
}

-- ===================== STATE READ/CSV =====================
local function read_state()
    return {
        health          = memory.readbyte(ADDR.health),
        opp_health      = memory.readbyte(ADDR.opp_health),
        opp_next_action = memory.readbyte(ADDR.opp_next_action),
        opp_timer       = memory.readbyte(ADDR.opp_timer),
        can_punch       = memory.readbyte(ADDR.can_punch),
        in_fight        = memory.readbyte(ADDR.in_fight),
        opp_knocked     = memory.readbyte(ADDR.opp_knocked),
        hearts_lost     = memory.readbyte(ADDR.hearts_lost),
    }
end

local function state_to_csv(state)
    return string.format("%d,%d,%d,%d,%d,%d,%d,%d",
        state.health,
        state.opp_health,
        state.opp_next_action,
        state.opp_timer,
        state.can_punch,
        state.in_fight,
        state.opp_knocked,
        state.hearts_lost
    )
end

-- ===================== BUTTON PRESS =====================
local function press_buttons(action)
    local buttons = ACTIONS[action] or ACTIONS.NONE
    -- Hold 3 frames, release 6 frames (matches MCTS step)
    for i=1,3 do
        joypad.set(1, buttons)
        emu.frameadvance()
    end
    for i=1,6 do
        joypad.set(1, {})
        emu.frameadvance()
    end
end

-- ===================== MAIN LOOP =====================
print("Starting main fight loop...")

while true do
    local state = read_state()
    local csv = state_to_csv(state)

    client:send(csv .. "\n")
    local line, err = client:receive("*l")

    local action = "NONE"
    if line then
        action = line:match("^%s*(.-)%s*$") -- trim
    end

    -- Formal logging
    if action ~= "NONE" then
        print(string.format("Frame %d | Action: %-12s | Player HP: %2d | Opp HP: %2d | Opp Timer: %2d | Punch Ready: %d | Hearts Lost: %3d",
            emu.framecount(),
            action,
            state.health,
            state.opp_health,
            state.opp_timer,
            state.can_punch,
            state.hearts_lost
        ))
    end

    press_buttons(action)
end
