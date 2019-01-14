This is a collection of cogs for Eliza, who is an instantiation of the [Red Discord bot](https://github.com/Cog-Creators/Red-DiscordBot). To make
these cogs available for your own Red instance, use

    [p]repo add eliza https://github.com/rngesus-wept/eliza
    [p]cog update
    [p]cog install eliza $COG_NAME

Throughout this documentation, when Eliza is said to listen for a message, she is listening only in
the same channel that the relevant command was issued, with a timeout of 5 minutes.


# **faq**

Maintain a per-guild database of frequently asked questions (FAQs). FAQs are managed by moderators,
and are searchable only by moderator-defined tags (i.e. not by question nor answer text). Eliza uses
this cog for rulings associated with games popular on the guilds she oversees.

A moderator can begin the creation of an FAQ entry using `[p]faq new <question>`. If `<question>` is
omitted, Eliza will instead listen for the next message from the invoking user, and take that as the
question. (This latter method of question creation is suggested, as discord.py's input parsing may
get stuck on questions containing special characters like `(` and `"`.) Regardless of how the question
was entered, Eliza will then listen for the next message from the invoking user and take that input
as the answer to the question, confirming entry creation in an embed with the entry's ID.

Existing entries can be further modified by a moderator, using `[p]faq edit-q <id>` and
`[p]faq edit-a <id>` to change the entry's question and answer respectively, and
`[p]faq tag <id> <tag1> [<tag2>...]` to add tags to the entry. Multi-word tags should be contained
in quotes. Tags beginning with a hyphen `-` are instead removed from the entry's tag list, e.g.
`[p]faq tag 10 -wrong`.

Users can request that Eliza show a FAQ entry by using `[p]faq search <tag1> [<tag2>...]` to list all
entries that have *all* the listed tags; or by using `[p]faq show <id>` to show specific entry.


# **lfg**

Maintain per-guild queues of people looking to playing particular games. LFG queues (henceforth
simply "queues") are created and managed by admins. Guild members can join and leave particular
queues, query the contents of queues, and challenge other members who are waiting in queue.

An admin can begin the creation of an LFG queue using `[p]queue create <name>`. This initializes the
queue using the given name, which should be case-insensitive-unique among all queue names. In
particular, an @-able role is created in the guild as "LFG <name>" using the capitalization provided
by the admin, but future references to the queue through commands (including administrative
commands) will be case-insensitive. Queues can be deleted by admins using `[p]queue delete <name>`.
All extant queues can be listed by `[p]queue list`.

By default, whenever Eliza responds to LFG-related commands, she will respond in the channel that
the command was issued in. To change this behavior, an admin should use `[p]queue sethome <channel>`
to route all the appropriate output to that channel instead.

Members can join an LFG queue by using `[p]lfg <name>`, which accepts an additional optional argument
`time` indicating the amount of time that member will remain in that queue, in minutes. If this
argument is not provided, it is presumed to be a guild-specific default, which is normally 60 but
may be configured by an admin using `[p]queue settime <minutes>`. Eliza maintains an invariant that as
long as a member is in an LFG queue that member will also possess the corresponding role for that
queue. It is then easy to communicate with people in that queue by @-ing the role; for example, for
negotiation of game parameters.


# **remindme**


# **secretkeeper**


# **todo**

