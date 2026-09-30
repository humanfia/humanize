# One account, every backend that could be run as it.
#
# A vendor's credential is the vendor's rather than the CLI's, so an account made for one is
# often an account several others could be run as. The key typed here is the words
# `not-a-real-key`, the way in is one that runs nothing, and nothing signs in to anything.

Output "/out/alike.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 620
Set Padding 12
Set Framerate 10
Set TypingSpeed 35ms

Hide
Type "cd /work/demo && clear" Enter
Show

# Off camera, because it is the walk rather than the thing: the prompt, `/settings accounts`,
# `add an account`, and `key` -- which is a variable rather than a login, so it asks and runs
# nothing. The stills below are of each step all the same.
Hide
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Type "/settings accounts" Enter
Wait+Screen /as local/
Tab
Enter
Wait+Screen /account name/
Down
Enter
Down 2
Enter
Wait+Screen /API key/
# What it is called: the name written in for it is replaced by the first letter typed.
Up
Type "shared"
Enter
# And the key -- which is the words `not-a-real-key`, and is drawn as bullets whatever it
# is. Typed off camera all the same: a key being typed is not a thing to film.
Type "not-a-real-key"
Enter
Show
Sleep 1200ms

# And then the question this is about: an Anthropic key is an Anthropic key whoever holds
# it, so there is a row for each backend that could be run as this account, on the same form.
Screenshot "/out/alike.png"
Sleep 800ms

# The ones this machine has installed start on; the rest are two keypresses away, the list
# each drops opening on the answer it is not.
Up 3
Sleep 500ms
Enter
Enter
Sleep 700ms
Enter
Enter
Sleep 1200ms
Down
Sleep 500ms
Enter

# And they are accounts of their own from here on, under the same name.
Wait+Screen /also saved for/
Sleep 2s
Screenshot "/out/alike-copied.png"
Sleep 400ms
