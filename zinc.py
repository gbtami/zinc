import os
import chess
import chess.uci

EngineFiles = ['../Stockfish/test', '../Stockfish/master']
DrawRule = {'movenumber': 40, 'movecount': 8, 'score': 20}
ResignRule = {'movecount': 3, 'score': 500}
Openings = '../book5.epd'
Concurrency = 7

engines = []
for i in range(0, 2):
    engines.append(chess.uci.popen_engine(EngineFiles[i]))
    engines[i].uci()
    engines[i].isready()
    engines[i].ucinewgame()
    engines[i].name = os.path.split(engineFiles[i])[1]

board = chess.Board()

while (not board.is_game_over(True)):
    stm = board.turn
    engines[stm].position(board)
    bestmove, ponder = engines[stm].go(movetime=100)
    board.push(bestmove)

print(board.result(True))
for i in range(0, 2):
    engines[i].quit()
