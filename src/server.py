# server.py
import socket
import threading
import json
import time
import random
import traceback
import sys
from constants import *


class PongServer:
    def __init__(self):
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.state = {
            "p1_y": SCREEN_HEIGHT // 2,
            "p2_y": SCREEN_HEIGHT // 2,
            "bx": SCREEN_WIDTH // 2,
            "by": SCREEN_HEIGHT // 2,
            "bdx": BALL_SPEED * random.choice([-1, 1]),
            "bdy": BALL_SPEED * random.choice([-1, 1]),
            "score": [0, 0],
        }
        self.state_lock = threading.Lock()
        self.running = True
        self.tick_count = 0
        self.game_active = False

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        server_sock.bind(("0.0.0.0", SERVER_PORT))
        server_sock.listen(5)
        server_sock.settimeout(1.0)
        print(f"Server started on 0.0.0.0:{SERVER_PORT}. Waiting for players...")

        try:
            while self.running:
                try:
                    conn, addr = server_sock.accept()
                    self._handle_new_connection(conn, addr)
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        print("Socket error")
                    break

                with self.clients_lock:
                    if len(self.clients) >= 2 and not self.game_active:
                        self._start_game()

        except KeyboardInterrupt:
            print("Shutdown requested")
        except Exception as e:
            print(f"Server error: {e}")
            traceback.print_exc()
        finally:
            self.shutdown(server_sock)

    def _handle_new_connection(self, conn, addr):
        with self.clients_lock:
            if len(self.clients) >= 2:
                conn.sendall(json.dumps({"type": "full"}).encode() + b"\n")
                conn.close()
                print(f"Rejected connection from {addr}: server full")
                return

            side = 1 if not any(c["side"] == 1 for c in self.clients.values()) else 2
            self.clients[conn] = {"side": side, "up": False, "down": False, "addr": addr}

        conn.sendall(json.dumps({"type": "assigned", "side": side}).encode() + b"\n")
        print(f"Player {side} connected: {addr}")

        if not any(t.name == f"input_handler_{id(conn)}" for t in threading.enumerate()):
            t = threading.Thread(target=self.handle_input, args=(conn,), daemon=True, name=f"input_handler_{id(conn)}")
            t.start()

    def _start_game(self):
        print("Game started: 2 players connected")
        self.game_active = True
        self.tick_count = 0
        with self.state_lock:
            self.state["score"] = [0, 0]
            self._reset_ball()

    def handle_input(self, conn):
        buffer = b""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer and self.running:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "input":
                            action = msg.get("action")
                            with self.clients_lock:
                                if conn in self.clients:
                                    if action == "stop":
                                        self.clients[conn]["up"] = False
                                        self.clients[conn]["down"] = False
                                    else:
                                        self.clients[conn]["up"] = action == "up"
                                        self.clients[conn]["down"] = action == "down"
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            self._handle_disconnect(conn)

    def _handle_disconnect(self, conn):
        with self.clients_lock:
            info = self.clients.pop(conn, None)
            if info:
                print(f"Player {info['side']} disconnected: {info.get('addr', 'unknown')}")
            remaining = len(self.clients)

        if remaining == 0:
            print("No players left. Waiting for new connections...")
            self.game_active = False
            with self.state_lock:
                self.state["score"] = [0, 0]
                self._reset_ball()
        elif remaining == 1:
            print("One player left. Waiting for opponent...")
            self.game_active = False
        try:
            conn.close()
        except:
            pass

    def game_loop(self):
        dt = 1.0 / TICK_RATE
        while self.running:
            if not self.game_active:
                time.sleep(0.1)
                with self.clients_lock:
                    if len(self.clients) >= 2:
                        self._start_game()
                continue

            frame_start = time.perf_counter()
            self.update()
            self.broadcast()
            elapsed = time.perf_counter() - frame_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.tick_count += 1

    def update(self):
        with self.clients_lock:
            for conn, info in self.clients.items():
                target = "p1_y" if info["side"] == 1 else "p2_y"
                current = self.state[target]
                if info["up"]:
                    current = min(SCREEN_HEIGHT - PADDLE_HEIGHT // 2, current + PADDLE_SPEED)
                if info["down"]:
                    current = max(PADDLE_HEIGHT // 2, current - PADDLE_SPEED)
                self.state[target] = current

        with self.state_lock:
            self.state["bx"] += self.state["bdx"]
            self.state["by"] += self.state["bdy"]

            if self.state["by"] - BALL_SIZE < 0 or self.state["by"] + BALL_SIZE > SCREEN_HEIGHT:
                self.state["bdy"] *= -1
                self.state["by"] = max(BALL_SIZE, min(SCREEN_HEIGHT - BALL_SIZE, self.state["by"]))

            if (self.state["bx"] - BALL_SIZE <= 40 + PADDLE_WIDTH and
                    self.state["p1_y"] - PADDLE_HEIGHT // 2 <= self.state["by"] <= self.state[
                        "p1_y"] + PADDLE_HEIGHT // 2 and
                    self.state["bdx"] < 0):
                self._bounce_off_paddle(1)

            if (self.state["bx"] + BALL_SIZE >= SCREEN_WIDTH - 40 - PADDLE_WIDTH and
                    self.state["p2_y"] - PADDLE_HEIGHT // 2 <= self.state["by"] <= self.state[
                        "p2_y"] + PADDLE_HEIGHT // 2 and
                    self.state["bdx"] > 0):
                self._bounce_off_paddle(2)

            if self.state["bx"] - BALL_SIZE < 0:
                self.state["score"][1] += 1
                self._reset_ball()
            elif self.state["bx"] + BALL_SIZE > SCREEN_WIDTH:
                self.state["score"][0] += 1
                self._reset_ball()

    def _bounce_off_paddle(self, player_side):
        self.state["bdx"] = -self.state["bdx"]
        new_speed = min(BALL_SPEED * 1.5, abs(self.state["bdx"]) * 1.03)
        self.state["bdx"] = new_speed * (1 if self.state["bdx"] > 0 else -1)
        paddle_y = self.state["p1_y"] if player_side == 1 else self.state["p2_y"]
        hit_offset = (self.state["by"] - paddle_y) / (PADDLE_HEIGHT / 2)
        self.state["bdy"] += hit_offset * 1.5
        current_speed = (self.state["bdx"] ** 2 + self.state["bdy"] ** 2) ** 0.5
        if current_speed > 0:
            target_speed = min(BALL_SPEED * 1.5, max(BALL_SPEED, current_speed))
            factor = target_speed / current_speed
            self.state["bdx"] *= factor
            self.state["bdy"] *= factor
        if player_side == 1:
            self.state["bx"] = 40 + PADDLE_WIDTH + BALL_SIZE + 1
        else:
            self.state["bx"] = SCREEN_WIDTH - 40 - PADDLE_WIDTH - BALL_SIZE - 1

    def _reset_ball(self):
        self.state["bx"], self.state["by"] = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        direction = random.choice([-1, 1])
        angle = random.uniform(-0.7, 0.7)
        self.state["bdx"] = BALL_SPEED * direction
        self.state["bdy"] = BALL_SPEED * angle

    def broadcast(self):
        with self.state_lock:
            payload = json.dumps({
                **self.state,
                "server_time": time.time(),
                "tick": self.tick_count
            }) + "\n"
            data = payload.encode()
        with self.clients_lock:
            conns = list(self.clients.keys())
        for conn in conns:
            try:
                conn.sendall(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._handle_disconnect(conn)

    def shutdown(self, server_sock):
        self.running = False
        with self.clients_lock:
            for conn in list(self.clients.keys()):
                try:
                    conn.close()
                except:
                    pass
            self.clients.clear()
        try:
            server_sock.close()
        except:
            pass
        print("Server stopped.")


if __name__ == "__main__":
    print("Starting Pong server...")
    server = PongServer()
    threading.Thread(target=server.game_loop, daemon=True).start()
    server.start()