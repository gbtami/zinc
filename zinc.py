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
import os, subprocess, time, threading
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
Games = 20
Concurrency = 7

class UCI():
    def __init__(self, engine):
        self.process = subprocess.Popen(engine['file'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, universal_newlines=True)
        self.name = engine['name']
        self.debug = engine['debug']
        self.options = []

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

    def newgame(self):
        self.writeline('ucinewgame')

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

class Game():
    def __init__(self, engines):
        assert len(engines) == 2
        self.engines = []
        for i in range(2):
            self.engines.append(UCI(engines[i]))
            self.engines[i].uci()
            for name in Options[i]:
                if name not in self.engines[i].options:
                    print('warning: "{}" is not a valid UCI Option for engine "{}"'.format(name, self.engines[i].name))
            self.engines[i].setoption(Options[i])
            self.engines[i].isready()

    def play_move(self, turnIdx, whiteIdx):
        def to_msec(sec):
            return int(sec * 1000)

        startTime = time.time()
        bestmove, score = self.engines[turnIdx].go({
            'depth': self.timeControls[turnIdx]['depth'],
            'nodes': self.timeControls[turnIdx]['nodes'],
            'movetime': self.timeControls[turnIdx]['movetime'],
            'wtime': to_msec(self.timeControls[whiteIdx]['time']),
            'btime': to_msec(self.timeControls[whiteIdx ^ 1]['time']),
            'winc': to_msec(self.timeControls[whiteIdx]['inc']),
            'binc': to_msec(self.timeControls[whiteIdx ^ 1]['inc'])
        })
        elapsed = time.time() - startTime

        self.timeControls[turnIdx]['time'] -= elapsed
        if self.timeControls[turnIdx]['time'] < 0:
            raise TimeoutError
        self.timeControls[turnIdx]['time'] += self.timeControls[turnIdx]['inc']
        return bestmove, score

    def play_game(self, fen, whiteIdx, timeControls):
        board = chess.Board(fen)
        turnIdx = whiteIdx ^ (board.turn == chess.BLACK)
        uciMoves = []
        self.timeControls = timeControls
        for e in self.engines:
            e.newgame()

        drawCnt, resignCnt = 0, 0 # in plies
        lostOnTime = None

        while (not board.is_game_over(True)):
            posCmd = 'position fen ' + fen
            if uciMoves:
                posCmd += ' moves ' + ' '.join(uciMoves)
            self.engines[turnIdx].writeline(posCmd)
            self.engines[turnIdx].isready()

            try:
                bestmove, score = self.play_move(turnIdx, whiteIdx)
            except TimeoutError:
                lostOnTime = turnIdx
                break

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
            turnIdx ^= 1

        result, reason = board.result(True), 'chess rules'
        if result == '*':
            if lostOnTime != None:
                result = '1-0' if lostOnTime == whiteIdx else '0-1'
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

        # Return numeric score, from engine #0 perspective
        scoreWhite = 1.0 if result == '1-0' else (0 if result == '0-1' else 0.5)
        return result, scoreWhite if whiteIdx == 0 else 1 - scoreWhite

    def __del__(self):
        for e in self.engines:
            e.quit()

class GamePool():
    def __init__(self, concurrency):
        self.concurrency = concurrency
        self.lock = threading.Lock()
        self.threads, self.games = [], []
        for i in range(concurrency):
            self.games.append(Game(Engines))
            self.threads.append(threading.Thread(target=self.play_games, args=(i,)))

    def run(self, jobs, timeControls):
        self.timeControls = timeControls
        self.jobs = jobs
        self.jobIdx = 0

        for t in self.threads:
            t.start()

        for thread in self.threads:
            thread.join()

    def play_games(self, threadIdx):
        while True:
            self.lock.acquire()
            jobIdx = self.jobIdx
            if jobIdx >= len(self.jobs):
                self.lock.release()
                return
            self.jobIdx += 1
            self.lock.release()

            result, score = self.games[threadIdx].play_game(
                self.jobs[jobIdx]['fen'],
                self.jobs[jobIdx]['white'],
                self.timeControls)

            print('Game #{}: {} vs. {}: {}'.format(
                jobIdx, Engines[jobs[jobIdx]['white']]['name'],
                Engines[jobs[jobIdx]['white'] ^ 1]['name'], result
            ))

jobs = []
with open(Openings, 'r') as f:
    for i in range(0, Games, 2):
        fen = f.readline().split(';')[0]
        if fen == '':
            f.seek(0)
        else:
            jobs.append({'fen': fen, 'white': 0})
            if i + 1 < Games:
                jobs.append({'fen': fen, 'white': 1})

GamePool(Concurrency).run(jobs, TimeControls)

if Games >= 2:
    # Print statistics
    score = statistics.mean(results)
    margin = 1.96 * statistics.stdev(results) / math.sqrt(Games)
    print('score = %.2f%% +/- %.2f%%' % (100 * score, 100 * margin))
