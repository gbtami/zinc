#!/usr/bin/python3
import os
import chess, chess.uci
from multiprocessing import Pool
import math, statistics

# Parameters
Engine = [
    {'file': '../Stockfish/test', 'name' : 'test'},
    {'file': '../Stockfish/base', 'name' : 'base'}
]
TimeControl = {'depth': None, 'nodes': None, 'movetime': 100}
Draw = {'movenumber': 40, 'movecount': 8, 'score': 20}
Resign = {'movecount': 3, 'score': 500}
Openings = '../book5.epd'
Games = 50
Concurrency = 7

def play(game):
    # Start engines
    engines = []
    for i in range(0, 2):
        engines.append(chess.uci.popen_engine(Engine[i]['file']))
        engines[i].uci()
        engines[i].ucinewgame()
        engines[i].name = Engine[i]['name']
        engines[i].info_handlers.append(chess.uci.InfoHandler())

    # Setup the position, and determine which engine plays first
    board = chess.Board(game['fen'])
    i = game['white'] ^ (board.turn == chess.BLACK)

    # Play the game
    drawCnt, resignCnt = 0, 0 # in plies
    while (not board.is_game_over(True)):
        engines[i].position(board)
        engines[i].isready()

        bestmove, ponder = engines[i].go(
            depth = TimeControl['depth'],
            nodes = TimeControl['nodes'],
            movetime = TimeControl['movetime']
        )

        score = engines[i].info_handlers[0].info['score'][1].cp
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

        board.push(bestmove)
        i ^= 1

    result = board.result(True)

    # Determine result in case of adjudication
    if result == '*':
        if resignCnt >= Resign['movecount']:
            if score > 0:
                result = '1-0' if board.turn == chess.WHITE else '0-1'
            else:
                result = '0-1' if board.turn == chess.WHITE else '1-0'
        else:
            result = '1/2-1/2'

    # Display results
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
        if i + 1 < Games:
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
