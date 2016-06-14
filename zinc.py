#!/usr/bin/python3
import os
import chess, chess.uci
from multiprocessing import Pool
import math, statistics

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

    # Setup the position, and determine which engine plays first
    board = chess.Board(game['fen'])
    idx = game['white'] ^ (board.turn == chess.BLACK)

    # Play the game
    while (not board.is_game_over(True)):
        engines[idx].position(board)
        bestmove, ponder = engines[idx].go(depth=8)
        board.push(bestmove)
        idx ^= 1

    # Display results
    result = board.result(True)
    print('Game #%d: %s vs. %s: %s' % (game['idx'] + 1, engines[game['white']].name,
        engines[game['white'] ^ 1].name, result))

    # Close engines
    for i in range(0, 2):
        engines[i].quit()

    # Return numeric score, from engine #0 perspective
    scoreWhite = 1.0 if result == "1-0" else (0 if result == "0-1" else 0.5)
    return scoreWhite if game['white'] == 0 else 1 - scoreWhite

# Prepare game elements of the form [idx, fen, white], where
# idx: game index, in range(0, Games)
# fen: starting position
# white: which engine plays white (0 or 1)
games = []
f = open(Openings, 'r')
for i in range(0, Games, 2):
    fen = f.readline().split(';')[0]
    if fen == '':
        f.seek(0)
    else:
        games.append({'idx': i, 'fen': fen, 'white': 0})
        if (i + 1 < Games):
            games.append({'idx': i + 1, 'fen': fen, 'white': 1})

# Play games, concurrently
pool = Pool(processes=Concurrency)
results = pool.map(play, games)
pool.close()
pool.join()

# Print statistics
score = statistics.mean(results)
margin = 1.96 * statistics.stdev(results) / math.sqrt(Games)
print('score = %.2f%% +/- %.2f%%' % (100 * score, 100 * margin))
