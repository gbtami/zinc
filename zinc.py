#!/usr/bin/python3
import os, subprocess, multiprocessing, time
import math, statistics
import chess

# Parameters
Engines = [
    {'file': '../Stockfish/test', 'name' : 'test'},
    {'file': '../Stockfish/base', 'name' : 'base'}
]
Options = [
    {'Hash': 16, 'Threads': 1},
    {'Hash': 16, 'Threads': 1}
]
TimeControl = {'depth': None, 'nodes': None, 'movetime': None, 'time': 2, 'inc': 0.02}
Draw = {'movenumber': 40, 'movecount': 8, 'score': 20}
Resign = {'movecount': 3, 'score': 500}
Openings = '../book5.epd'
Debug=False
Games = 10
Concurrency = 2

class UCI(object):
    def __init__(self, cmd, name, debug):
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, universal_newlines=True)
        self.name = name
        self.debug = debug
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

def start_engine(i):
    e = UCI(Engines[i]['file'], Engines[i]['name'], Debug)
    e.uci()

    for name in Options[i]:
        if name not in e.options:
            print('warning: "%s" is not a valid UCI Option for engine "%s"' % (name, e.name))

    e.setoption(Options[i])
    e.isready()
    e.writeline('ucinewgame')
    return e

def to_msec(sec):
    return int(sec * 1000)

def play(game):
    # Start engines and clocks
    engines, clocks = [], []
    for i in range(0, 2):
        engines.append(start_engine(i))
        clocks.append(TimeControl['time'])

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
        engines[i].writeline(posCmd)
        engines[i].isready()

        startTime = time.time()
        bestmove, score = engines[i].go({
            'depth': TimeControl['depth'],
            'nodes': TimeControl['nodes'],
            'movetime': TimeControl['movetime'],
            'wtime': to_msec(clocks[game['white']]),
            'btime': to_msec(clocks[game['white'] ^ 1]),
            'winc': to_msec(TimeControl['inc']),
            'binc': to_msec(TimeControl['inc'])
        })
        elapsed = time.time() - startTime

        clocks[i] -= elapsed

        if (clocks[i] < 0):
            lostOnTime = i
            break

        clocks[i] += TimeControl['inc']

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
    print('Game #%d: %s vs. %s: %s (%s)' % (game['idx'] + 1, engines[game['white']].name,
        engines[game['white'] ^ 1].name, result, reason))

    # Close engines
    for i in range(0, 2):
        engines[i].quit()

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
