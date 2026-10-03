# What one run leaves behind: a directory, and everything the run was.
#
# The runs were invented by stage.py, sessions and all -- written down by the code that
# writes down a real one. Nothing here starts a backend.

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 500
Set Padding 12
Set Framerate 15
Set TypingSpeed 25ms

Hide
Type "cd /work/demo && clear" Enter
Type "run=$(ls -d /root/.hmz/epics/-work-demo/*/ | tail -1)" Enter
Type "clear" Enter
Show

Sleep 500ms
# One run of one flow is one directory: what happened, what the flow left behind, the
# programs it ran, and every conversation it opened.
Type 'ls "$run"' Enter
Sleep 2200ms
Screenshot "/out/run.png"
Sleep 600ms

# Its conversations are kept in it, a directory per CLI laid out as that CLI's home is:
# the only copy there is, which the CLI wrote there and resumes from there.
Type 'cd "$run" && find sessions -type f' Enter
Sleep 3s
Screenshot "/out/run-kept.png"
Sleep 600ms

# What a flow that says it can be picked up left for the next run of it: the engine's
# journal, whose `set` lines are the state `--resume` hands back.
Type 'cat "$run"resume.jsonl' Enter
Sleep 2800ms
