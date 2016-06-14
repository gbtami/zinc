#!/usr/bin/python3
import os
import chess
import chess.uci

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

    # Setup board with given FEN start position game[0]
    board = chess.Board(game[0])
    whiteIdx = game[1] ^ (board.turn == chess.BLACK) # which engine is white ?

    # Play game: game[1] is the idx of the engine playing first
    idx = game[1]
    while (not board.is_game_over(True)):
        engines[idx].position(board)
        bestmove, ponder = engines[idx].go(depth=10)
        board.push(bestmove)
        idx ^= 1

    # Store game result
    game[2] = board.result(True)

    # Pretty-print result
    print('%s vs. %s: %s' % (engines[whiteIdx].name, engines[whiteIdx ^ 1].name, game[2]))

    # Close engines
    for i in range(0, 2):
        engines[i].quit()

# Prepare game elements of the form [fen, idx, result], where
# fen is the starting position
# idx is 0 or 1 says which engine plays the first move
# result is None for now, and will be updated once games are played
games = []
f = open(Openings, 'r')
for i in range(0, Games, 2):
    fen = f.readline().split(';')[0]
    if fen == '':
        f.seek(0)
    else:
        games.append([fen, 0, None])
        games.append([fen, 1, None])

# Play games, sequentially for the moment
for g in games:
    play(g)
