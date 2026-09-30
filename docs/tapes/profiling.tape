# Whether a run here is profiled as well as traced, which is a thing about this directory.
#
# Nothing runs: the switch is written down, and what it does is done by the next flow that
# runs here. The programs in the trace beside it were invented by stage.py.

Output "/out/profiling.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

Type "/settings" Enter
Wait+Screen /Workspace/
Sleep 2s

# Its six pages, and into the second: what is remembered about this directory.
Down
Sleep 500ms
Enter
Wait+Screen /Profiling/
Sleep 1400ms
Screenshot "/out/profiling.png"
Sleep 400ms
