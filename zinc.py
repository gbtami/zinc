#!/usr/bin/python3
import os
import chess
import chess.uci
from multiprocessing import Pool

EngineFiles = ['../Stockfish/test', '../Stockfish/master']
DrawRule = {'movenumber': 40, 'movecount': 8, 'score': 20}
ResignRule = {'movecount': 3, 'score': 500}
Openings = '../book5.epd'
Games = 50
Concurrency = 7

def play(game):
    # Start engines
    engines = []
    for i in range(0, 2):
        engines.append(chess.uci.popen_engine(EngineFiles[i]))
        engines[i].uci()
        engines[i].isready()
        engines[i].ucinewgame()
        engines[i].name = os.path.split(EngineFiles[i])[1]

    # Setup board with given FEN start position game[1]
    board = chess.Board(game[1])
    whiteIdx = game[2] ^ (board.turn == chess.BLACK) # which engine is white ?

    # Play game: game[2] is the idx of the engine playing first
    idx = game[2]
    while (not board.is_game_over(True)):
        engines[idx].position(board)
        bestmove, ponder = engines[idx].go(depth=8)
        board.push(bestmove)
        idx ^= 1

    # Pretty-print result
    result = board.result(True)
    print('Game #%d: %s vs. %s: %s' % (game[0] + 1, engines[whiteIdx].name, engines[whiteIdx ^ 1].name, result))

    # Close engines
    for i in range(0, 2):
        engines[i].quit()

    return result

# Prepare game elements of the form [gameIdx, fen, engineIdx], where
# gameIdx: game index, in range(0, Games)
# fen: starting position
# engineIdx: which engine plays the first move (0 or 1)
games = []
f = open(Openings, 'r')
for i in range(0, Games, 2):
    fen = f.readline().split(';')[0]
    if fen == '':
        f.seek(0)
    else:
        games.append([i, fen, 0])
        if (i + 1 < Games):
            games.append([i + 1, fen, 1])

# Play games, concurrently
pool = Pool(processes=Concurrency)
results = pool.map(play, games)
pool.close()
pool.join()

for r in results:
    print(r)