# Completion: what the prompt offers to finish a half-typed word with, and taking one.
#
# Nothing is sent. Every line is finished and then cleared with ctrl+c, so no flow starts
# and no turn is taken: the backends here are stand-ins that run nothing.

Output "/out/completion.gif"

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

# `/` lists every command, with what it takes and what it is for.
Type "/"
Sleep 2200ms
Down
Sleep 500ms
Down
Sleep 900ms

# More letters narrow the list; tab takes the one under the cursor.
Type "fl"
Sleep 1400ms
Down
Sleep 700ms
Tab
Sleep 1600ms

# A command written out in full shows what it takes instead.
Ctrl+C
Sleep 500ms
Type "/afk"
Sleep 1800ms
Ctrl+C
Sleep 500ms

# `$` offers the flows, under the sigil that starts one.
Type "$"
Sleep 1800ms
Type "lo"
Sleep 1200ms
Tab
Sleep 500ms
Type " add a subtract function"
Sleep 1800ms
Ctrl+C
Sleep 800ms
