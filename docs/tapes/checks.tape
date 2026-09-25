# Everything knowable before the first turn is checked before the first turn.
#
# No agent runs in this tape. Each line below is refused by `hmz exec` itself.

Output "/out/checks.gif"

Set Shell "bash"
Set FontSize 16
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 20
Set TypingSpeed 30ms

Hide
Type "cd /work/demo && clear" Enter
Show

Sleep 500ms
Type "cat .humanize/flows/twice/__init__.py" Enter
Sleep 3s

# No budget: refused before any agent starts, since a run with nothing to stop it is not one to
# start by accident.
Type `hmz exec -f twice -a builder=claude/claude-opus-4-8:high "fix the build"` Enter
Sleep 2500ms

# The flow declares a role, `builder`, and nothing fills it.
Type `hmz exec -f twice -b cost=5 "fix the build"` Enter
Sleep 3s

# And a flow that is not there.
Type `hmz exec -f nosuchflow -a builder=claude/claude-opus-4-8:high -b cost=5 "fix the build"` Enter
Sleep 3s
