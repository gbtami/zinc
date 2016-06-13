import sys
import chess
import chess.uci

engines = []
for i in range(0, 2):
    engines.append(chess.uci.popen_engine(sys.argv[i + 1]))
    engines[i].uci()
    engines[i].isready()
    engines[i].ucinewgame()

board = chess.Board()

while (not board.is_game_over(True)):
    stm = board.turn
    engines[stm].position(board)
    bestmove, ponder = engines[stm].go(movetime=100)
    board.push(bestmove)

print(board.result(True))
for i in range(0, 2):
    engines[i].quit()
