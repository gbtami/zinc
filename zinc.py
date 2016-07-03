#!/usr/bin/python3
# Zinc, a chess engine testing tool. Copyright 2016 lucasart.
#
# Zinc is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version
# 3 of the License, or (at your option) any later version.
#
# Zinc is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this
# program. If not, see <http://www.gnu.org/licenses/>.

import collections
import datetime
import math
import multiprocessing
import statistics
import subprocess
import time

import chess
import chess.polyglot
import chess.pgn

# Parameters
Engines = [
    {'file': '../Stockfish/test', 'name': 'test', 'debug': False},
    {'file': '../Stockfish/base', 'name': 'base', 'debug': False}
]
Options = [
    {'Hash': 16, 'Threads': 1},
    {'Hash': 16, 'Threads': 1}
]
TimeControls = [
    {'depth': None, 'nodes': None, 'movetime': None, 'time': 2, 'inc': 0.02,
        'movestogo': None},
    {'depth': None, 'nodes': None, 'movetime': None, 'time': 2, 'inc': 0.02,
        'movestogo': None}
]
Draw = {'movenumber': 40, 'movecount': 8, 'score': 20}
Resign = {'movecount': 3, 'score': 500}
Openings = '../chess960.epd'
BookDepth = None
PgnOut = './out.pgn'
Chess960 = True
Games = 20
Concurrency = 7
RatingInterval = 10


class UCI():
    def __init__(self, engine):
        self.process = subprocess.Popen(engine['file'], stdout=subprocess.PIPE,
            stdin=subprocess.PIPE, universal_newlines=True, bufsize=1)
        self.name = engine['name']
        self.debug = engine['debug']
        self.options = []

    def readline(self):
        line = self.process.stdout.readline().rstrip()
        if self.debug:
            print('{}({}) > {}'.format(self.name, self.process.pid, line))
        return line

    def writeline(self, string):
        if self.debug:
            print('{}({}) < {}'.format(self.name, self.process.pid, string))
        self.process.stdin.write(string + '\n')

    def uci(self):
        self.writeline('uci')
        while True:
            line = self.readline()
            if line.startswith('option name '):
                tokens = line.split()
                name = tokens[2:tokens.index('type')]
                self.options.append(' '.join(name))
            elif line == 'uciok':
                break

    def setoptions(self, options):
        for name in options:
            value = options[name]
            if type(value) is bool:
                value = str(value).lower()
            self.writeline('setoption name {} value {}'.format(name, value))

    def isready(self):
        self.writeline('isready')
        while self.readline() != 'readyok':
            pass

    def newgame(self):
        self.writeline('ucinewgame')

    def go(self, args):
        tokens = ['go']
        for name in args:
            if args[name] is not None:
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


class Clock():
    def __init__(self, timeControl):
        self.timeControl = timeControl
        self.time = timeControl['time']
        self.movestogo = timeControl['movestogo']

    def consume(self, seconds):
        if self.time is not None:
            self.time -= seconds
            if self.time < 0:
                raise TimeoutError
            if self.timeControl['inc']:
                self.time += self.timeControl['inc']

        if self.movestogo is not None:
            self.movestogo -= 1
            if self.movestogo <= 0:
                self.movestogo = self.timeControl['movestogo']
                if self.timeControl['time']:
                    self.time += self.timeControl['time']


class Game():
    def __init__(self, engines):
        assert len(engines) == 2
        self.engines = []
        for i in range(2):
            self.engines.append(UCI(engines[i]))
            self.engines[i].uci()
            for name in Options[i]:
                if name not in self.engines[i].options:
                    print('warning: "{}" is not a valid UCI Option for engine "{}"'
                        .format(name, self.engines[i].name))
            self.engines[i].setoptions(Options[i])
            if Chess960:
                self.engines[i].setoptions({'UCI_Chess960': True})
            self.engines[i].isready()

    def play_move(self, turnIdx, whiteIdx):
        def to_msec(seconds):
            return int(seconds * 1000) if seconds is not None else None

        startTime = time.time()

        bestmove, score = self.engines[turnIdx].go({
            'depth': self.clocks[turnIdx].timeControl['depth'],
            'nodes': self.clocks[turnIdx].timeControl['nodes'],
            'movetime': self.clocks[turnIdx].timeControl['movetime'],
            'wtime': to_msec(self.clocks[whiteIdx].time),
            'btime': to_msec(self.clocks[whiteIdx ^ 1].time),
            'winc': to_msec(self.clocks[whiteIdx].timeControl['inc']),
            'binc': to_msec(self.clocks[whiteIdx ^ 1].timeControl['inc']),
            'movestogo': self.clocks[turnIdx].movestogo
        })

        elapsed = time.time() - startTime
        self.clocks[turnIdx].consume(elapsed)

        return bestmove, score

    def play_game(self, fen, whiteIdx, timeControls, returnPgn=False, pgnRound=None):
        board = chess.Board(fen, Chess960)
        turnIdx = whiteIdx ^ (board.turn == chess.BLACK)
        self.clocks = [Clock(timeControls[0]), Clock(timeControls[1])]
        for e in self.engines:
            e.newgame()

        drawPlyCnt, resignPlyCnt = 0, 0
        lostOnTime = None
        posCmd = ['position fen ', fen]

        while (not board.is_game_over(True)):
            self.engines[turnIdx].writeline(' '.join(posCmd))
            self.engines[turnIdx].isready()

            try:
                bestmove, score = self.play_move(turnIdx, whiteIdx)
            except TimeoutError:
                lostOnTime = turnIdx
                break

            if score is not None:
                # Resign adjudication
                if abs(score) >= Resign['score']:
                    resignPlyCnt += 1
                    if resignPlyCnt >= 2 * Resign['movecount']:
                        break
                else:
                    resignPlyCnt = 0

                # Draw adjudication
                if abs(score) <= Draw['score']:
                    drawPlyCnt += 1
                    if drawPlyCnt >= 2 * Draw['movecount'] \
                            and board.fullmove_number >= Draw['movenumber']:
                        break
                else:
                    drawPlyCnt = 0
            else:
                # Disable adjudication over mate scores
                drawPlyCnt, resignPlyCnt = 0, 0

            if board.move_stack:
                posCmd.append(bestmove)
            else:
                posCmd += ['moves', bestmove]

            board.push_uci(bestmove)
            turnIdx ^= 1

        result, reason = board.result(True), 'chess rules'
        if result == '*':
            if lostOnTime is not None:
                result = '1-0' if lostOnTime == whiteIdx else '0-1'
                reason = 'lost on time'
            elif resignPlyCnt >= 2 * Resign['movecount']:
                reason = 'adjudication'
                if score > 0:
                    result = '1-0' if board.turn == chess.WHITE else '0-1'
                else:
                    result = '0-1' if board.turn == chess.WHITE else '1-0'
            else:
                result = '1/2-1/2'
                reason = 'adjudication'

        if returnPgn:
            game = chess.pgn.Game.from_board(board)
            game.headers['White'] = self.engines[whiteIdx].name
            game.headers['Black'] = self.engines[whiteIdx ^ 1].name
            game.headers['Result'] = result
            game.headers['Date'] = datetime.date.today().isoformat()
            game.headers['Round'] = pgnRound
            exporter = chess.pgn.StringExporter(variations=False, comments=False)
            pgnText = game.accept(exporter)
        else:
            pgnText = None

        # Return numeric score, from engine #0 perspective
        scoreWhite = 1.0 if result == '1-0' else (0 if result == '0-1' else 0.5)
        return result, scoreWhite if whiteIdx == 0 else 1 - scoreWhite, pgnText


class GamePool():
    def __init__(self, concurrency, pgnOut):
        self.concurrency = concurrency
        self.processes = []

        # I/O objects for the process pool
        self.jobQueue = multiprocessing.Queue()
        self.resultQueue = multiprocessing.Queue()
        self.pgnOut = pgnOut

        # Get the processes ready
        for i in range(concurrency):
            process = multiprocessing.Process(target=play_games,
                args=(self.jobQueue, self.resultQueue, pgnOut))
            self.processes.append(process)

    def run(self, jobs, timeControls):
        # Fill jobQueue with games
        for j in jobs:
            self.jobQueue.put(j)

        # Insert 'None' padding values as a stopping buffer
        for i in range(self.concurrency):
            self.jobQueue.put(None)

        try:
            for p in self.processes:
                p.start()

            scores = []
            for i in range(0, len(jobs)):
                r = self.resultQueue.get()
                print(r.display)

                scores.append(r.score)
                if (i+1) % RatingInterval == 0 and len(scores) >= 2:
                    mean = statistics.mean(scores)
                    margin = 1.96 * math.sqrt(statistics.variance(scores) / len(scores))
                    print('score of {} vs. {} = {:.2f}% +/- {:.2f}%'.format(
                        Engines[0]['name'], Engines[1]['name'], 100*mean, 100*margin))

                if self.pgnOut:
                    with open(self.pgnOut, 'a') as f:
                        print(r.pgnText, file=f, end='\n\n')

            for p in self.processes:
                p.join()

        except KeyboardInterrupt:
            pass  # processes are dead already


def play_games(jobQueue, resultQueue, pgnOut):
    try:
        game = Game(Engines)

        while True:
            # HACK: We can't just test jobQueue.empty(), then run jobQueue.get(). Between
            # both operations, another process could steal a job from the queue. That's
            # why we insert some padding 'None' values at the end of the queue
            job = jobQueue.get()
            if job is None:
                return

            result, score, pgnText = game.play_game(job.fen, job.white, TimeControls,
                pgnOut, job.round)

            display = 'Game #{} ({} vs. {}): {}'.format(
                job.round, Engines[job.white]['name'],
                Engines[job.white ^ 1]['name'], result)

            resultQueue.put(Result(score=score, display=display, pgnText=pgnText))

    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    Job = collections.namedtuple('Job', 'round fen white')
    Result = collections.namedtuple('Result', 'score display pgnText')

    jobs = []
    if Openings.endswith('.epd'):  # EPD
        with open(Openings, 'r') as f:
            for i in range(0, Games, 2):
                fen = f.readline().rstrip().split(';')[0]
                if fen == '':
                    f.seek(0)
                else:
                    jobs.append(Job(round=i+1, fen=fen, white=0))
                    if i + 1 < Games:
                        jobs.append(Job(round=i+2, fen=fen, white=1))
    else:  # PolyGlot
        assert Openings.endswith('.bin')
        with chess.polyglot.open_reader(Openings) as book:
            for i in range(0, Games, 2):
                board = chess.Board(chess960=Chess960)
                while (BookDepth is None) or (board.fullmove_number <= BookDepth):
                    board.push(book.weighted_choice(board).move(Chess960))
                fen = board.fen()
                jobs.append(Job(round=i+1, fen=fen, white=0))
                if i + 1 < Games:
                    jobs.append(Job(round=i+2, fen=fen, white=1))

    GamePool(Concurrency, PgnOut).run(jobs, TimeControls)
