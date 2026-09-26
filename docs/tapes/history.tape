# History: up and down walk back through what was sent here, and give back the line that was
# being typed when the walk started.
#
# The lines sent are commands that change what is shown and nothing else. No flow starts and
# no turn is taken: the backends here are stand-ins that run nothing.

Output "/out/history.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 520
Set Padding 12
Set Framerate 10
Set TypingSpeed 50ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

# Three lines sent, each of which is now in the history.
Type "/details on" Enter
Sleep 900ms
Type "/afk on" Enter
Sleep 900ms
Type "/details off" Enter
Sleep 900ms

# Half a line, and then up: the newest first, one further back each press.
Type "fix the flaky"
Sleep 1000ms
Up
Sleep 1100ms
Up
Sleep 1100ms
Up
Sleep 1400ms

# Down comes forward again, and past the newest gives back what was being typed.
Down
Sleep 900ms
Down
Sleep 900ms
Down
Sleep 2000ms

Ctrl+C
Sleep 600ms
