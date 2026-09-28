# The terminal interface: the box it opens with, the commands, and the flow picker.
#
# No turn is taken. The backends here are stand-ins that run nothing, and the tape leaves
# before anything could be said to one.

Output "/out/tui.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 20
Set TypingSpeed 50ms

Hide
# Opening the flows fetches whatever has never been fetched, and this image has no git to fetch
# with, which `/flow` would say in red on camera: so `official` is marked as fetched out of frame,
# as first-run.tape does.
Type "cd /work/demo && mkdir -p /root/.humanize/flowverses/official/.git && clear" Enter
Show

Sleep 500ms
Type "hmz" Enter
Sleep 4s

# Type `/` and what the line could be is listed under the editor, a line about each.
Type "/"
Sleep 3s

Backspace
Sleep 500ms

# The flows there are, a tab per place they come from.
Type "/flow"
Sleep 1500ms
Enter
Sleep 3s

Right
Sleep 2500ms

Escape
Sleep 1500ms

# `/exit` is what leaves: ctrl+c ends a turn, and there is none here to end.
Type "/exit" Enter
Sleep 1500ms
