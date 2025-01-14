"""Module to manage trivia sessions."""
import asyncio
import time
import random
import re
from collections import Counter
import discord
from redbot.core import bank
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, bold, humanize_list, humanize_number
from redbot.core.utils.common_filters import normalize_smartquotes
from .log import LOG

__all__ = ["TriviaSession"]

T_ = Translator("TriviaSession", __file__)


_ = lambda s: s
_REVEAL_MESSAGES = (
    _("I know this one! {answer}!"),
    _("Easy: {answer}."),
    _("Oh really? It's {answer} of course."),
    _("Ah, sorry, I was looking for {answer}."),
)
_FAIL_MESSAGES = (
    _("To the next one I guess..."),
    _("Moving on..."),
    _("I'm sure you'll know the answer of the next one."),
    _("\N{PENSIVE FACE} Next one."),
)
# _ = T_


class TriviaSession:
    """Class to run a session of trivia with the user.

    To run the trivia session immediately, use `TriviaSession.start` instead of
    instantiating directly.

    Attributes
    ----------
    ctx : `commands.Context`
        Context object from which this session will be run.
        This object assumes the session was started in `ctx.channel`
        by `ctx.author`.
    question_list : `dict`
        A list of tuples mapping questions (`str`) to answers (`list` of
        `str`).
    settings : `dict`
        Settings for the trivia session, with values for the following:
         - ``max_score`` (`int`)
         - ``delay`` (`float`)
         - ``timeout`` (`float`)
         - ``slow_reveal`` (`float`)
         - ``half_reveal`` (`float`)
         - ``reveal_answer`` (`bool`)
         - ``bot_plays`` (`bool`)
         - ``allow_override`` (`bool`)
         - ``payout_multiplier`` (`float`)
    scores : `collections.Counter`
        A counter with the players as keys, and their scores as values. The
        players are of type `discord.Member`.
    count : `int`
        The number of questions which have been asked.

    """

    def __init__(self, ctx, question_list: dict, settings: dict):
        self.ctx = ctx
        list_ = list(question_list.items())
        random.shuffle(list_)
        self.question_list = list_
        self.settings = settings
        self.scores = Counter()
        self.count = 0
        self._last_response = time.time()
        self._task = None

    @classmethod
    def start(cls, ctx, question_list, settings):
        """Create and start a trivia session.

        This allows the session to manage the running and cancellation of its
        own tasks.

        Parameters
        ----------
        ctx : `commands.Context`
            Same as `TriviaSession.ctx`
        question_list : `dict`
            Same as `TriviaSession.question_list`
        settings : `dict`
            Same as `TriviaSession.settings`

        Returns
        -------
        TriviaSession
            The new trivia session being run.

        """
        session = cls(ctx, question_list, settings)
        loop = ctx.bot.loop
        session._task = loop.create_task(session.run())
        return session

    async def run(self):
        """Run the trivia session.

        In order for the trivia session to be stopped correctly, this should
        only be called internally by `TriviaSession.start`.
        """
        await self._send_startup_msg()
        max_score = self.settings["max_score"]
        delay = self.settings["delay"]
        timeout = self.settings["timeout"]
        slow_reveal = self.settings["slow_reveal"]
        half_reveal = self.settings["half_reveal"]
        for question, answers in self._iter_questions():
            async with self.ctx.typing():
                await asyncio.sleep(3)
            self.count += 1

            # Allow for subentries of questions to also specify certain settings
            delay_factor, reveal_s, reveal_h = 1.0, slow_reveal, half_reveal
            for entry in answers:
                if isinstance(entry, dict):
                    # delay_factor: Multiply the amount of time given for this question by this amount
                    delay_factor = entry.get('delay_factor', delay_factor)
                    # slow_reveal: Reveal a random letter of the answer every {this many} seconds
                    reveal_s = entry.get('slow_reveal', reveal_s)
                    # half_reveal: Reveal half the letters in this many seconds, capped by slow_reveal
                    reveal_h = entry.get('half_reveal', reveal_h)
            answers = list(filter(lambda x: isinstance(x, str), answers))

            msg = bold(_("Question number {num}!").format(num=self.count)) + "\n\n" + question
            await self.ctx.send(msg)
            continue_ = await self.wait_for_answer(answers, delay * delay_factor, timeout,
                                                   slow_reveal=reveal_s, half_reveal=reveal_h)
            if continue_ is False:
                break
            if any(score >= max_score for score in self.scores.values()):
                await self.end_game()
                break
        else:
            await self.ctx.send(_("There are no more questions!"))
            await self.end_game()

    async def _send_startup_msg(self):
        list_names = []
        for idx, tup in enumerate(self.settings["lists"].items()):
            name, author = tup
            if author:
                title = _("{trivia_list} (by {author})").format(trivia_list=name, author=author)
            else:
                title = name
            list_names.append(title)
        await self.ctx.send(
            _("Starting Trivia: {list_names}").format(list_names=humanize_list(list_names))
        )

    def _iter_questions(self):
        """Iterate over questions and answers for this session.

        Yields
        ------
        `tuple`
            A tuple containing the question (`str`) and the answers (`tuple` of
            `str`).

        """
        for question, answers in self.question_list:
            answers = _parse_answers(answers)
            yield question, answers

    async def wait_for_answer(self, answers, delay: float, timeout: float,
                              slow_reveal: float = 0.0, half_reveal: float = 0.0):
        """Wait for a correct answer, and then respond.

        Scores are also updated in this method.

        Returns False if waiting was cancelled; this is usually due to the
        session being forcibly stopped.

        Parameters
        ----------
        answers : `iterable` of `str`
            A list of valid answers to the current question.
        delay : float
            How long users have to respond (in seconds).
        timeout : float
            How long before the session ends due to no responses (in seconds).
        slow_reveal : float
            Every [this many] seconds, reveal a random letter from the answer. (default = 0.0 for no reveals)
        half_reveal : float
            Over [this many] seconds, half of the letters of the answer will be revealed one
            letter at a time (but never any faster than one every `slow_reveal` seconds).

        Returns
        -------
        bool
            :code:`True` if the session wasn't interrupted.

        """
        try:
            if half_reveal:
                letter_count = len(re.findall(r'\w', answers[0]))
                slow_reveal = max(slow_reveal, 2.0 * half_reveal / letter_count)
            if slow_reveal:
                reveal_task = self.ctx.bot.loop.create_task(self.reveal_answer(answers[0], slow_reveal))
            message = await self.ctx.bot.wait_for(
                "message", check=self.check_answer(answers), timeout=delay
            )
        except asyncio.TimeoutError:
            if time.time() - self._last_response >= timeout:
                await self.ctx.send(_("Guys...? Well, I guess I'll stop then."))
                self.stop()
                return False
            if self.settings["reveal_answer"]:
                reply = T_(random.choice(_REVEAL_MESSAGES)).format(answer=answers[0])
            else:
                reply = T_(random.choice(_FAIL_MESSAGES))
            if self.settings["bot_plays"]:
                reply += _(" **+1** for me!")
                self.scores[self.ctx.guild.me] += 1
            await self.ctx.send(reply)
        else:
            self.scores[message.author] += 1
            reply = _("You got it {user}! **+1** to you!").format(user=message.author.display_name)
            await self.ctx.send(reply)
        finally:
            if slow_reveal:
                reveal_task.cancel()
        return True

    async def reveal_answer(self, answer, interval):
        """Slowly reveal random letters from a trivia answer."""
        full_answer = list(answer.upper())
        current_reveal = ['·' if char.isalnum() else char for char in full_answer]
        positions = [idx for idx, char in enumerate(current_reveal) if char == '·']
        random.shuffle(positions)

        while current_reveal != full_answer:
            await asyncio.sleep(interval)
            next_reveal = positions.pop()
            current_reveal[next_reveal] = full_answer[next_reveal]
            await self.ctx.send(f'`{"".join(current_reveal)}`')

    def check_answer(self, answers):
        """Get a predicate to check for correct answers.

        The returned predicate takes a message as its only parameter,
        and returns ``True`` if the message contains any of the
        given answers.

        Parameters
        ----------
        answers : `iterable` of `str`
            The answers which the predicate must check for.

        Returns
        -------
        function
            The message predicate.

        """
        answers = tuple(re.compile(f'\\b{s}\\b', re.I) for s in answers)

        def _pred(message: discord.Message):
            early_exit = message.channel != self.ctx.channel or message.author == self.ctx.guild.me
            if early_exit:
                return False

            self._last_response = time.time()
            guess = re.sub(r'\s+', ' ', message.content.strip().lower())
            guess = normalize_smartquotes(guess)
            for answer in answers:
                if answer.search(guess):
                    return True
            return False

        return _pred

    async def end_game(self):
        """End the trivia session and display scrores."""
        if self.scores:
            await self.send_table()
        multiplier = self.settings["payout_multiplier"]
        if multiplier > 0:
            await self.pay_winner(multiplier)
        self.stop()

    async def send_table(self):
        """Send a table of scores to the session's channel."""
        table = "+ Results: \n\n"
        for user, score in self.scores.most_common():
            table += "+ {}\t{}\n".format(user, score)
        await self.ctx.send(box(table, lang="diff"))

    def stop(self):
        """Stop the trivia session, without showing scores."""
        self.ctx.bot.dispatch("trivia_end", self)

    def force_stop(self):
        """Cancel whichever tasks this session is running."""
        self._task.cancel()
        channel = self.ctx.channel
        LOG.debug("Force stopping trivia session; #%s in %s", channel, channel.guild.id)

    async def pay_winner(self, multiplier: float):
        """Pay the winner of this trivia session.

        The winner is only payed if there are at least 3 human contestants.

        Parameters
        ----------
        multiplier : float
            The coefficient of the winner's score, used to determine the amount
            paid.

        """
        (winner, score) = next((tup for tup in self.scores.most_common(1)), (None, None))
        me_ = self.ctx.guild.me
        if winner is not None and winner != me_ and score > 0:
            contestants = list(self.scores.keys())
            if me_ in contestants:
                contestants.remove(me_)
            if len(contestants) >= 3:
                amount = int(multiplier * score)
                if amount > 0:
                    LOG.debug("Paying trivia winner: %d credits --> %s", amount, str(winner))
                    await bank.deposit_credits(winner, int(multiplier * score))
                    await self.ctx.send(
                        _(
                            "Congratulations, {user}, you have received {num} {currency}"
                            " for coming first."
                        ).format(
                            user=winner.display_name,
                            num=humanize_number(amount),
                            currency=await bank.get_currency_name(self.ctx.guild),
                        )
                    )


def _parse_answers(answers):
    """Parse the raw answers to readable strings.

    The reason this exists is because of YAML's ambiguous syntax. For example,
    if the answer to a question in YAML is ``yes``, YAML will load it as the
    boolean value ``True``, which is not necessarily the desired answer. This
    function aims to undo that for bools, and possibly for numbers in the
    future too.

    Parameters
    ----------
    answers : `iterable` of `str`
        The raw answers loaded from YAML.

    Returns
    -------
    `tuple` of `str`
        The answers in readable/ guessable strings.

    """
    ret = []
    dicts = []
    for answer in answers:
        if isinstance(answer, bool):
            if answer is True:
                ret.extend(["True", "Yes", "On"])
            else:
                ret.extend(["False", "No", "Off"])
        elif isinstance(answer, dict):
            dicts.append(answer)
        else:
            ret.append(str(answer))
    # Uniquify list
    seen = set()
    return tuple(dicts) + tuple(x for x in ret if not (x in seen or seen.add(x)))
