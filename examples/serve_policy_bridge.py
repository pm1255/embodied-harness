"""Loopback JSON bridge for an operator-supplied policy factory.

python examples/serve_policy_bridge.py --factory my_policy:create --port 8907
Factory returns an object with .metadata and .infer(message) -> {actions: Hx14}.
The bridge decodes RGB bytes; policy owns preprocessing and checkpoint normalization.
Use an SSH tunnel for a remote worker. This server has no robot control channel.
"""
import argparse
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import traceback

import numpy as np
from embodied_harness.adapters import load_factory


def serve(policy, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, payload):
            raw = json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.respond(200 if self.path == "/metadata" else 404,
                         policy.metadata if self.path == "/metadata" else {"error": "unknown_route"})

        def do_POST(self):
            try:
                if self.path != "/infer":
                    raise ValueError("Unknown route")
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 16 * 1024 * 1024:
                    raise ValueError("Invalid request size")
                message = json.loads(self.rfile.read(length))
                decoded = {}
                for slot, frame in message.pop("images").items():
                    shape = frame["shape"]
                    if len(shape) != 3 or shape[-1] != 3 or any(type(x) is not int or not 0 < x <= 2048 for x in shape):
                        raise ValueError("Invalid RGB shape")
                    decoded[slot] = np.frombuffer(base64.b64decode(frame["data"], validate=True),
                                                 dtype=np.uint8).reshape(shape).copy()
                message["camera_slots"] = decoded
                self.respond(200, policy.infer(message))
            except Exception as exc:
                traceback.print_exc()
                self.respond(400, {"error": type(exc).__name__})
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True)
    parser.add_argument("--port", type=int, default=8907)
    args = parser.parse_args()
    serve(load_factory(args.factory)(), args.port)
