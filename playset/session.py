import asyncio
import random
from collections import Counter
from redbot.core.utils.chat_formatting import box
from redbot.core.data_manager import cog_data_path
import discord
import numpy as np
import matplotlib.pyplot as pp
import os
import wget
from zipfile import ZipFile

__all__ = ["SetSession"]

_CARD_SIZE = (84,61)
_VALID_TRIPLES = [(0,0,0),(1,1,1),(2,2,2),(0,1,2),(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)]
_LETTER_MAP = {"A":(0,0),"B":(0,1),"C":(0,2),"D":(0,3),"E":(0,4),"F":(0,5),"G":(0,6),
               "H":(1,0),"I":(1,1),"J":(1,2),"K":(1,3),"L":(1,4),"M":(1,5),"N":(1,6),
               "O":(2,0),"P":(2,1),"R":(2,2),"S":(2,3),"T":(2,4),"U":(2,5),"V":(2,6)}
               


class SetSession:
    def __init__(self, ctx):
        self.dataDir = str(cog_data_path(self))
        if not 'cards' in self.dataDir:
            url = 'https://frky-storage.s3-us-west-1.amazonaws.com/cards.zip'
            wget.download(url, self.dataDir+'/cards.zip')
            zip = ZipFile(self.dataDir+'/cards.zip')
            zip.extractall(self.dataDir)
            zip.close()
        self.dataDir = self.dataDir+'/cards'
        self.ctx = ctx
        self.scores = Counter()
        self.deck = np.random.permutation(81)
        self.boardW = 4
        self.board = np.zeros((3,self.boardW),dtype=int)
        for i in range(self.board.size):
            self.board[i%3,i//3] = self.deck[0]
            self.deck = self.deck[1:]
        while not _board_contains_set(self.board):
            self.boardW += 1
            oldBoard = self.board
            self.board = np.zeros((3,self.boardW),dtype=int)
            for i in range(oldBoard.size):
                self.board[i%3][i//3] = oldBoard[i%3][i//3]
            for i in range(3):
                self.board[i][self.boardW-1] = self.deck[0]
                self.deck = self.deck[1:]
        self._gen_board_image()
        
    @classmethod
    def start(cls, ctx):
        session = cls(ctx)
        loop = ctx.bot.loop
        session._task = loop.create_task(session.run())
        return session
        
    async def run(self):
        await self._send_startup_msg()
        self.game_running = True
        while self.game_running:
            await asyncio.sleep(2)
            f = discord.File(self.dataDir+'/board.png')
            await self.ctx.send(file=f)
            foundSet = await self.wait_for_set()
            await self._update_board(foundSet)
            if _board_contains_set(self.board):
                self._gen_board_image()
            else:
                self.game_running = False
                
        await self.end_game()
        
    async def _send_startup_msg(self):
        await self.ctx.send("Starting Set. Type in the three card letters to call a set. Incorrect calls are -1 point. Good luck")
        await asyncio.sleep(3)

    async def wait_for_set(self):
        self.foundSet = False
        self.wrongAnswers = []

        message = await asyncio.gather(self.ctx.bot.wait_for("message", check=self.check_set),self._wrong_handler())
        guess = message[0].content.upper()
        cards = []
        for i in range(3):
            cards.append(self.board[_LETTER_MAP[guess[i]]])
        self.scores[message[0].author] += 1
        await self.ctx.send(str(message[0].author)+": Set! +1 point")
   
        return cards
        
    async def _wrong_handler(self):
        while ((not self.foundSet) or len(self.wrongAnswers)>0):
            if(len(self.wrongAnswers)>0):
                m = self.wrongAnswers[0]
                self.scores[m.author] -= 1
                await self.ctx.send(str(m.author)+": not a set. -1 point")
                self.wrongAnswers = self.wrongAnswers[1:]
            else: 
                await asyncio.sleep(.25)
        
    def check_set(self, message: discord.Message):
        early_exit = message.channel != self.ctx.channel or message.author == self.ctx.guild.me
        if early_exit:
            return False
        guess = message.content.upper()
        if len(guess) != 3:
            return False
        if guess[0]==guess[1] or guess[0]==guess[2] or guess[1]==guess[2]:
            return False
        validLetters = []
        for l in _LETTER_MAP:
            if _LETTER_MAP[l][1]<self.boardW:
                validLetters.append(l)
        for i in range(3):
            if not guess[i] in validLetters:
                return False
        cards = []
        for i in range(3):
            cards.append(self.board[_LETTER_MAP[guess[i]]])
        if not _is_set(cards):
            self.wrongAnswers.append(message)
            return False
        self.foundSet = True
        return True
        
    async def _update_board(self,cards):
        if (self.boardW>4) or (len(self.deck) == 0):
            #try reducing
            oldBoard = self.board
            self.boardW -= 1
            self.board = np.zeros((3,self.boardW),dtype=int)
            newi = 0
            for i in range(oldBoard.size):
                if oldBoard[i%3,i//3] not in cards:
                    self.board[newi%3,newi//3] = oldBoard[i%3,i//3]
                    newi += 1
        else:
            #replace missing cards
            for i in range(self.board.size):
                if self.board[i%3,i//3] in cards:
                    self.board[i%3,i//3] = self.deck[0]
                    self.deck = self.deck[1:]
                    
        while (not _board_contains_set(self.board)) and (len(self.deck) != 0):
            #repair boards while possible
            self.boardW += 1
            oldBoard = self.board
            self.board = np.zeros((3,self.boardW),dtype=int)
            for i in range(oldBoard.size):
                self.board[i%3][i//3] = oldBoard[i%3][i//3]
            for i in range(3):
                self.board[i][self.boardW-1] = self.deck[0]
                self.deck = self.deck[1:]
            
    async def end_game(self):
        """End the Set game and display scrores."""
        if self.scores:
            await self.send_table()
        self.stop()

    async def send_table(self):
        """Send a table of scores to the session's channel."""
        table = "+ Results: \n\n"
        for user, score in self.scores.most_common():
            table += "+ {}\t{}\n".format(user, score)
        await self.ctx.send(box(table, lang="diff"))

    def stop(self):
        """Stop the Set session, without showing scores."""
        self.ctx.bot.dispatch("set_end", self)

    def force_stop(self):
        """Cancel whichever tasks this session is running."""
        self._task.cancel()
        channel = self.ctx.channel
        print("Force stopping Set session; "+str(channel)+" in "+str(channel.guild.id))     
        
    def _gen_board_image(self):
        image = np.zeros((self.board.shape[0]*_CARD_SIZE[1],
                          self.board.shape[1]*_CARD_SIZE[0],
                          4))
        for i in range(self.board.shape[0]):
            for j in range(self.board.shape[1]):
                v = _card_num_to_vec(self.board[i][j])
                card = pp.imread(self.dataDir+'/'+str(v[0])+str(v[1])+str(v[2])+str(v[3])+'.png')
                image[i*_CARD_SIZE[1]:(i+1)*_CARD_SIZE[1],j*_CARD_SIZE[0]:(j+1)*_CARD_SIZE[0]]=card
        overlay = pp.imread(self.dataDir+'/overlay.png')
        for i in range(image.shape[0]):
            for j in range(image.shape[1]):
                image[i][j][0] *= overlay[i][j][0]
                image[i][j][1] *= overlay[i][j][1]
                image[i][j][2] *= overlay[i][j][2]
        pp.imsave(self.dataDir+'/board.png',image)
    
def _is_set(cardList):
    vecs = [_card_num_to_vec(card) for card in cardList]
    for i in range(4):
        if not (vecs[0][i],vecs[1][i],vecs[2][i]) in _VALID_TRIPLES:
            return False
    return True
    
def _board_contains_set(board):
    for i in range(board.size):
        for j in range(i+1,board.size):
            for k in range(j+1,board.size):
                cards = [board[i%3,i//3],board[j%3,j//3],board[k%3,k//3]]
                if _is_set(cards):
                    return True
    return False
    
def _card_num_to_vec(cardNum):
    return [int(cardNum//27),int((cardNum//9)%3),int((cardNum//3)%3),int(cardNum%3)]
