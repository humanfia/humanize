# A first run, set up: `/flow`, a flow, its one agent, what a run may spend, and saving.
#
# No turn is taken. The backends here are stand-ins that run nothing, and the task is typed
# and never sent. Nothing is fetched either: the official index is the one `stage.py` wrote
# into this container, and the flow set up is the project's own `twice`.

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 520
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms
Set CursorBlink false
# The container answers a key more slowly than a desktop does, and a menu read at that pace
# is a menu nobody waits for.
Set PlaybackSpeed 1.5

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 600ms

# The flows ready to run here: the built-in ones, then each place the rest came from. The
# cursor opens on the one this directory was last set up on.
Type@10ms "/flow"
Sleep 300ms
Enter
Wait+Screen /Flows ready to run here/
Sleep 1200ms
Enter
Wait+Screen /Configure each role/
Sleep 1500ms

# Its one role, `builder`: the CLI, the account, the model, and the effort.
Enter
Wait+Screen /Set up builder/
Sleep 1200ms
Down
Down
Sleep 400ms
Enter
Wait+Screen /Select a model for claude/
Sleep 1200ms
Down
Sleep 500ms
Enter
Wait+Screen /claude-sonnet-4-8 ▸/
Sleep 500ms
Down
Sleep 400ms
# The effort is picked from the model's own list: enter drops it under the row, the arrows
# walk it, enter takes one.
Enter
Wait+Screen /╭─ effort/
Sleep 700ms
Down
Sleep 400ms
Enter
Wait+Screen /medium ▾/
Sleep 900ms
# And `Save`, the button under the rows, hands the agent back to the menu: tab is the way
# down to it.
Tab
Wait+Screen /enter save/
Sleep 400ms
Enter
Wait+Screen /sonnet-4-8:medium ▸/
Sleep 1s

# What a run of it may spend: a limit to stop at, of time, money or output.
Down
Sleep 400ms
Enter
Wait+Screen /Set budget for/
Sleep 1s
Enter
Type "20m"
Sleep 500ms
Enter
Sleep 300ms
Tab
Wait+Screen /enter set/
Sleep 400ms
Enter
Wait+Screen /stops at 20m/
Sleep 1500ms

# Saved by the menu's own `Save`, the last of its buttons.
Tab
Wait+Screen /enter save/
Sleep 400ms
Enter
Wait+Screen /builder · claude\/claude-sonnet-4-8:medium/
Sleep 1500ms

# The task is the next thing said. Typed here, and never sent.
Type "Fix the bug in calc.py."
Sleep 2500ms

Hide
Ctrl+C
Type "/exit" Enter
Sleep 500ms
