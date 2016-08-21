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

from __future__ import print_function  # Python 2.7 compatibility
{'You need Python 2.7+ or Python 3.1+'}  # Syntax error in earlier Python version

import collections
import datetime
import math
import multiprocessing
import subprocess
import time

import chess
import chess.polyglot
import chess.pgn
import chess.syzygy

# Parameters
Engines = [
    {'file': '../Stockfish/master', 'name': 'master', 'debug': False},
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
Games = 10
Concurrency = 7
RatingInterval = 10
Tournament = 'round-robin'  # 'gauntlet'
SyzygyPath = '../syzygy'  # None


class UCIEngine():
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


class TimeoutError(Exception):  # Python 2.7 compatibility
    pass


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


def play_move(uciEngine, clocks, turnIdx, whiteIdx):
    def to_msec(seconds):
        return int(seconds * 1000) if seconds is not None else None

    startTime = time.time()

    bestmove, score = uciEngine.go({
        'depth': clocks[turnIdx].timeControl['depth'],
        'nodes': clocks[turnIdx].timeControl['nodes'],
        'movetime': clocks[turnIdx].timeControl['movetime'],
        'wtime': to_msec(clocks[whiteIdx].time),
        'btime': to_msec(clocks[whiteIdx ^ 1].time),
        'winc': to_msec(clocks[whiteIdx].timeControl['inc']),
        'binc': to_msec(clocks[whiteIdx ^ 1].timeControl['inc']),
        'movestogo': clocks[turnIdx].movestogo
    })

    elapsed = time.time() - startTime
    clocks[turnIdx].consume(elapsed)

    return bestmove, score


def play_game(uciEngines, fen, whiteIdx, timeControls, tablebases, returnPgn=False,
        pgnRound=None):
    board = chess.Board(fen, Chess960)
    turnIdx = whiteIdx ^ (board.turn == chess.BLACK)
    clocks = [Clock(timeControls[0]), Clock(timeControls[1])]

    for e in uciEngines:
        e.newgame()

    drawPlyCnt, resignPlyCnt = 0, 0
    lostOnTime, wdl = None, None
    posCmd = ['position fen', fen]

    while (not board.is_game_over(True)):
        uciEngines[turnIdx].writeline(' '.join(posCmd))
        uciEngines[turnIdx].isready()

        if board.halfmove_clock == 0:
            wdl = tablebases.probe_wdl(board)
            if wdl is not None:
                break

        try:
            bestmove, score = play_move(uciEngines[turnIdx], clocks, turnIdx, whiteIdx)
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
            reason = 'resign'
            if score > 0:
                result = '1-0' if board.turn == chess.WHITE else '0-1'
            else:
                result = '0-1' if board.turn == chess.WHITE else '1-0'
        elif wdl is not None:
            reason = 'tb adjudication'
            if wdl == -2:
                result = '1-0' if board.turn == chess.WHITE else '0-1'
            elif wdl == 2:
                result = '0-1' if board.turn == chess.WHITE else '1-0'
            else:
                result = '1/2-1/2'
        else:
            result = '1/2-1/2'
            reason = 'draw adjudication'

    if returnPgn:
        game = chess.pgn.Game.from_board(board)
        game.headers['White'] = uciEngines[whiteIdx].name
        game.headers['Black'] = uciEngines[whiteIdx ^ 1].name
        game.headers['Result'] = result
        game.headers['Date'] = datetime.date.today().isoformat()
        game.headers['Round'] = pgnRound
        game.headers['FEN'] = fen
        exporter = chess.pgn.StringExporter(variations=False, comments=False)
        pgnText = game.accept(exporter)
        pgnText += '\n{{{}}}'.format(reason)
    else:
        pgnText = None

    # Return numeric score, from engine #0 perspective
    scoreWhite = 1.0 if result == '1-0' else (0 if result == '0-1' else 0.5)
    return result, scoreWhite if whiteIdx == 0 else 1 - scoreWhite, pgnText


def print_score(engines, scores):
    N = len(scores)
    if N >= 2:
        mean = sum(scores) / N
        variance = sum((x - mean)**2 for x in scores) / (N - 1)
        margin = 1.96 * math.sqrt(variance / N)
        print('score of {} vs. {} = {:.2f}% +/- {:.2f}%'.format(
            engines[0]['name'], engines[1]['name'], 100*mean, 100*margin))


def run_pool(engines, fens, tablebases, timeControls, concurrency, pgnOut):
    # I/O objects for the process pool
    jobQueue = multiprocessing.Queue()
    resultQueue = multiprocessing.Queue()

    # Prepare the processes
    processes = []
    assert len(engines) == 2  # Tournaments should be managed by the caller
    for i in range(concurrency):
        process = multiprocessing.Process(target=play_games,
            args=(engines, jobQueue, resultQueue, tablebases, pgnOut))
        processes.append(process)

    # Prepare the jobQueue
    for idx, fen in enumerate(fens):
        jobQueue.put(Job(round=idx+1, fen=fen, white=idx % 2))

    # Insert 'None' padding values as a stopping buffer
    for i in range(concurrency):
        jobQueue.put(None)

    try:
        for p in processes:
            p.start()

        scores = []
        for i in range(0, len(fens)):
            r = resultQueue.get()
            print(r.display)

            scores.append(r.score)
            if (i+1) % RatingInterval == 0:
                print_score(engines, scores)

            if pgnOut:
                with open(pgnOut, 'a') as f:
                    print(r.pgnText, file=f, end='\n\n')

        for p in processes:
            p.join()

    except KeyboardInterrupt:
        print_score(engines, scores)


def init_engine(engine, options):
    uciEngine = UCIEngine(engine)
    uciEngine.uci()

    for name in options:
        if name not in uciEngine.options:
            print('warning: "{}" is not a valid UCI Option for engine "{}"'
                .format(name, uciEngine.name))

    uciEngine.setoptions(options)

    if Chess960:
        uciEngine.setoptions({'UCI_Chess960': True})

    uciEngine.isready()

    return uciEngine


def play_games(engines, jobQueue, resultQueue, tablebases, pgnOut):
    try:
        uciEngines = []
        for i, e in enumerate(engines):
            uciEngines.append(init_engine(e, Options[i]))

        while True:
            # HACK: We can't just test jobQueue.empty(), then run jobQueue.get(). Between
            # both operations, another process could steal a job from the queue. That's
            # why we insert some padding 'None' values at the end of the queue
            job = jobQueue.get()
            if job is None:
                return

            result, score, pgnText = play_game(uciEngines, job.fen, job.white,
                TimeControls, tablebases, pgnOut, job.round)

            display = 'Game #{} ({} vs. {}): {}'.format(
                job.round, engines[job.white]['name'],
                engines[job.white ^ 1]['name'], result)

            resultQueue.put(Result(score=score, display=display, pgnText=pgnText))

    except KeyboardInterrupt:
        pass

Job = collections.namedtuple('Job', 'round fen white')
Result = collections.namedtuple('Result', 'score display pgnText')

if __name__ == '__main__':
    fens = []
    if Openings.endswith('.epd'):  # EPD
        with open(Openings, 'r') as f:
            for i in range(0, Games, 2):
                fen = f.readline().rstrip().split(';')[0]
                if fen == '':
                    f.seek(0)
                else:
                    fens.append(fen)
                    if i + 1 < Games:
                        fens.append(fen)
    else:  # PolyGlot
        assert Openings.endswith('.bin')
        with chess.polyglot.open_reader(Openings) as book:
            for i in range(0, Games, 2):
                board = chess.Board(chess960=Chess960)
                while (BookDepth is None) or (board.fullmove_number <= BookDepth):
                    board.push(book.weighted_choice(board).move(Chess960))
                fen = board.fen()
                fens.append(fen)
                if i + 1 < Games:
                    fens.append(fen)

    with chess.syzygy.open_tablebases(SyzygyPath) as tablebases:
        # Run the tournament
        assert len(Engines) >= 2
        if Tournament == 'gauntlet':
            for e in Engines[1:]:
                run_pool([Engines[0], e], fens, tablebases, TimeControls, Concurrency,
                    PgnOut)
        else:
            assert Tournament == 'round-robin'
            for i in range(len(Engines) - 1):
                for e in Engines[i+1:]:
                    run_pool([Engines[i], e], fens, tablebases, TimeControls, Concurrency,
                        PgnOut)
