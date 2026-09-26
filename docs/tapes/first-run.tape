# A first run, set up: `/flow`, a flow, its one agent, what a run may spend, and saving.
#
# No turn is taken. The backends here are stand-ins that run nothing, and the task is typed
# and never sent. Opening the flows fetches whatever has never been fetched, and this image
# has no git to fetch with, which `/flow` would say in red on camera. So `official` is marked
# as fetched out of frame: it then offers the flow in the package and nothing else, nothing
# is fetched, and the flow set up is the project's own `twice`.

Output "/out/first-run.gif"

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
Type "cd /work/demo && mkdir -p /root/.humanize/flowverses/official/.git && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 600ms

# The flows, a list per place they come from: the arrows step between the places.
Type "/flow"
Sleep 300ms
Enter
Wait+Screen /Which flow drives/
Sleep 1s
Right
Wait+Screen /local\/twice/
Sleep 700ms
Down
Sleep 600ms
Enter
Wait+Screen /What each of its roles/
Sleep 1500ms

# Its one role, `builder`: the CLI, the account, the model, and the effort.
Enter
Wait+Screen /Set up builder/
Sleep 1200ms
Down
Down
Sleep 400ms
Enter
Wait+Screen /Select what claude runs/
Sleep 1200ms
Down
Sleep 500ms
Enter
Wait+Screen /claude-sonnet-4-8 /
Sleep 500ms
Down
Sleep 500ms
Left
Wait+Screen /medium/
Sleep 1200ms
Ctrl+J
Wait+Screen /none yet/
Sleep 1s

# What a run of it may spend. A run of a flow like this one is given a budget.
Down
Sleep 400ms
Enter
Wait+Screen /may spend/
Sleep 1s
Type "20m"
Sleep 500ms
Enter
Wait+Screen /stops at/
Sleep 1500ms

# Saved from anywhere on the menu.
Ctrl+J
Wait+Screen /say what to do/
Sleep 1500ms

# The task is the next thing said. Typed here, and never sent.
Type "Fix the bug in calc.py."
Sleep 2500ms

Hide
Ctrl+C
Type "/exit" Enter
Sleep 500ms
