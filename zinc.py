#!/usr/bin/python3
# Zinc, a chess engine testing tool. Copyright 2016 lucasart.
#
# Zinc is free software: you can redistribute it and/or modify it under the terms of the GNU General
#  Public License as published by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Zinc is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not,
# see <http://www.gnu.org/licenses/>.
import os, subprocess, multiprocessing, time
import math, statistics
import chess

# Parameters
Engines = [
    {'file': '../Stockfish/test', 'name' : 'test', 'debug': False},
    {'file': '../Stockfish/base', 'name' : 'base', 'debug': False}
]
Options = [
    {'Hash': 16, 'Threads': 1},
    {'Hash': 16, 'Threads': 1}
]
TimeControls = [
    {'depth': None, 'nodes': None, 'movetime': None, 'time': 2, 'inc': 0.02},
    {'depth': None, 'nodes': None, 'movetime': None, 'time': 2, 'inc': 0.02}
]
Draw = {'movenumber': 40, 'movecount': 8, 'score': 20}
Resign = {'movecount': 3, 'score': 500}
Openings = '../book5.epd'
Games = 10
Concurrency = 1

class UCI(object):
    def __init__(self, engine):
        self.process = subprocess.Popen(engine['file'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, universal_newlines=True)
        self.name = engine['name']
        self.debug = engine['debug']
        self.options = []
        self.time = None

    def readline(self):
        line = self.process.stdout.readline()[:-1] # remove trailing '\n'
        if self.debug:
            print('{}({}) > {}'.format(self.name, self.process.pid, line))
        return line

    def writeline(self, string):
        if self.debug:
            print('{}({}) < {}'.format(self.name, self.process.pid, string))
        self.process.stdin.write(string)
        self.process.stdin.write('\n')
        self.process.stdin.flush()

    def uci(self):
        self.writeline('uci')
        while True:
            line = self.readline()
            if line.startswith('option name'):
                name = ''
                tokens = line.split()
                for i in range(2, len(tokens)):
                    if tokens[i] == 'type':
                        break
                    name += tokens[i] + ' '
                self.options.append(name[:-1])
            elif line == 'uciok':
                break

    def setoption(self, options):
        for name in options:
            self.writeline('setoption name {} value {}'.format(name, options[name]))

    def isready(self):
        self.writeline('isready')
        while self.readline() != 'readyok':
            pass

    def newgame(self, timeControl):
        self.writeline('ucinewgame')
        self.time = timeControl['time']

    def go(self, args):
        tokens = ['go']
        for name in args:
            if args[name]:
                tokens += [name, str(args[name])]
        self.writeline(' '.join(tokens))

        score = None
        while True:
            line = self.readline()
            if line.startswith('info'):
                i = line.find('score ')
                if i != -1:
                    tokens = line[(i + len('score ')):].split()
                    assert len(tokens) >= 2
                    if tokens[0] == 'cp':
                        if len(tokens) == 2 or not tokens[2].endswith('bound'):
                            score = int(tokens[1])
                    elif tokens[0] == 'mate':
                        score = math.copysign(Resign['score'], int(tokens[1]))

            elif line.startswith('bestmove'):
                return line.split()[1], score

    def quit(self):
        self.writeline('quit')
        self.process.wait()

class UCIPair(object):
    def __init__(self, engines):
        assert len(engines) == 2
        self.engines = []
        for i in range(0, 2):
            self.engines.append(UCI(engines[i]))
            self.engines[i].uci()
            for name in Options[i]:
                if name not in self.engines[i].options:
                    print('warning: "{}" is not a valid UCI Option for engine "{}"'.format(name, self.engines[i].name))
            self.engines[i].setoption(Options[i])
            self.engines[i].isready()

    def newgame(self, timeControls):
        for i in range(0, 2):
            self.engines[i].newgame(timeControls[i])

    def __del__(self):
        print('deleting pair')
        for i in range(0, 2):
            self.engines[i].quit()

def to_msec(sec):
    return int(sec * 1000)

def play(game):
    pair = UCIPair(Engines)
    pair.newgame(TimeControls)

    # Setup the position, and determine which engine plays first
    board = chess.Board(game['fen'])
    uciMoves = []
    i = game['white'] ^ (board.turn == chess.BLACK)

    # Play the game
    drawCnt, resignCnt = 0, 0 # in plies
    lostOnTime = None

    while (not board.is_game_over(True)):
        posCmd = 'position fen ' + game['fen']
        if uciMoves:
            posCmd += ' moves ' + ' '.join(uciMoves)
        pair.engines[i].writeline(posCmd)
        pair.engines[i].isready()

        startTime = time.time()
        bestmove, score = pair.engines[i].go({
            'depth': TimeControls[i]['depth'],
            'nodes': TimeControls[i]['nodes'],
            'movetime': TimeControls[i]['movetime'],
            'wtime': to_msec(pair.engines[game['white']].time),
            'btime': to_msec(pair.engines[game['white'] ^ 1].time),
            'winc': to_msec(TimeControls[i]['inc']),
            'binc': to_msec(TimeControls[i]['inc'])
        })
        elapsed = time.time() - startTime

        pair.engines[i].time -= elapsed

        if (pair.engines[i].time < 0):
            lostOnTime = i
            break

        pair.engines[i].time += TimeControls[i]['inc']

        if score != None:
            # Resign adjudication
            if abs(score) >= Resign['score']:
                resignCnt += 1
                if resignCnt >= 2 * Resign['movecount']:
                    break
            else:
                resignCnt=0

            # Draw adjudication
            if abs(score) <= Draw['score']:
                drawCnt += 1
                if drawCnt >= 2 * Draw['movecount'] and board.fullmove_number >= Draw['movenumber']:
                    break
            else:
                drawCnt = 0
        else:
            # Disable adjudication over mate scores
            drawCnt, resignCnt = 0, 0

        board.push_uci(bestmove)
        uciMoves.append(bestmove)
        i ^= 1

    result, reason = board.result(True), 'chess rules'

    # Determine result in case of adjudication
    if result == '*':
        if lostOnTime != None:
            result = '1-0' if lostOnTime == game['white'] else '0-1'
            reason = 'lost on time'
        elif resignCnt >= 2 * Resign['movecount']:
            reason = 'adjudication'
            if score > 0:
                result = '1-0' if board.turn == chess.WHITE else '0-1'
            else:
                result = '0-1' if board.turn == chess.WHITE else '1-0'
        else:
            result = '1/2-1/2'
            reason = 'adjudication'

    # Display results
    print('Game #%d: %s vs. %s: %s (%s)' % (game['idx'] + 1, pair.engines[game['white']].name,
        pair.engines[game['white'] ^ 1].name, result, reason))

    # Return numeric score, from engine #0 perspective
    scoreWhite = 1.0 if result == '1-0' else (0 if result == '0-1' else 0.5)
    return scoreWhite if game['white'] == 0 else 1 - scoreWhite

# Prepare game elements of the form [idx, fen, white], where
# idx: game index, in range(0, Games)
# fen: starting position
# white: which engine plays white (0 or 1)
games = []
with open(Openings, 'r') as f:
    for i in range(0, Games, 2):
        fen = f.readline().split(';')[0]
        if fen == '':
            f.seek(0)
        else:
            games.append({'idx': i, 'fen': fen, 'white': 0})
            if i + 1 < Games:
                games.append({'idx': i + 1, 'fen': fen, 'white': 1})

# Play games, concurrently
with multiprocessing.Pool(processes=Concurrency) as pool:
    results = pool.map(play, games)

if Games >= 2:
    # Print statistics
    score = statistics.mean(results)
    margin = 1.96 * statistics.stdev(results) / math.sqrt(Games)
    print('score = %.2f%% +/- %.2f%%' % (100 * score, 100 * margin))
