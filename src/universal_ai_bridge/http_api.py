from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .core import ApprovalRequired, BridgeError, BridgeService, Conflict, Forbidden, NotFound


class BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, service: BridgeService):
        host = server_address[0]
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("v0 HTTP server is loopback-only; external binding requires an authenticated deployment boundary")
        self.service = service
        super().__init__(server_address, BridgeRequestHandler)


class BridgeRequestHandler(BaseHTTPRequestHandler):
    server: BridgeHTTPServer

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep request logs free of request bodies and model position content.
        super().log_message(format, *args)

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > 1_000_000:
            raise ValueError("request body must be at most 1 MB")
        raw = self.rfile.read(length) if length else b"{}"
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON request body must be an object")
        return parsed

    def _principal(self, task_id: str) -> dict[str, str]:
        authorization = self.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            from .core import Unauthorized
            raise Unauthorized("send a task-scoped bearer token in the Authorization header")
        return self.server.service.authenticate_principal(task_id, token.strip())

    def _owner(self, task_id: str) -> dict[str, str]:
        principal = self._principal(task_id)
        if principal["role"] != "owner":
            raise Forbidden("this operation requires the task owner credential")
        return principal

    def _error(self, exc: Exception) -> None:
        from .core import Unauthorized
        if isinstance(exc, Unauthorized):
            status = 401
        elif isinstance(exc, NotFound):
            status = 404
        elif isinstance(exc, Forbidden):
            status = 403
        elif isinstance(exc, ApprovalRequired):
            status = 423
        elif isinstance(exc, Conflict):
            status = 409
        elif isinstance(exc, (ValueError, KeyError, json.JSONDecodeError)):
            status = 400
        elif isinstance(exc, BridgeError):
            status = 409
        else:
            status = 500
        self._send(status, {"error": type(exc).__name__, "message": str(exc)})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
        try:
            if parts == ["health"]:
                self._send(200, {"status": "ok", "agent_connections": "not_connected", "submission_mode": "manual"})
                return
            if len(parts) >= 2 and parts[0] == "tasks":
                task_id = parts[1]
                principal = self._principal(task_id)
                viewer = principal["name"] if principal["role"] == "participant" else "__task_owner__"
                if len(parts) == 2:
                    self._send(200, self.server.service.get_task(task_id))
                    return
                if len(parts) == 3 and parts[2] == "positions":
                    self._send(200, {"positions": self.server.service.list_positions(task_id, viewer)})
                    return
                if len(parts) == 3 and parts[2] == "export":
                    self._send(200, self.server.service.export_timeline(task_id, viewer=viewer))
                    return
            self._send(404, {"error": "NotFound", "message": "route not found"})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
        try:
            body = self._body()
            service = self.server.service
            if parts == ["tasks"]:
                result = service.create_task(
                    body.get("objective", ""), body.get("acceptance_criteria", []),
                    body.get("mode", "independent"), body.get("required_authors", []),
                )
                self._send(201, result)
                return
            if len(parts) >= 2 and parts[0] == "tasks":
                task_id = parts[1]
                if len(parts) == 3 and parts[2] == "positions":
                    principal = self._principal(task_id)
                    if principal["role"] != "participant":
                        raise Forbidden("only a participant credential may submit a position")
                    if "author" in body:
                        raise ValueError("author is derived from the bearer credential and must not be supplied")
                    result = service.submit_position(task_id, principal["name"], body.get("content", ""), actor=principal["name"])
                    self._send(201, result)
                    return

                principal = self._owner(task_id)
                actor = principal["name"]
                if len(parts) == 3 and parts[2] == "close":
                    self._send(200, service.close_collection(task_id, actor=actor, note=body.get("note", "manual close")))
                    return
                if len(parts) == 3 and parts[2] == "reveal":
                    self._send(200, service.reveal(task_id, actor=actor))
                    return
                if len(parts) == 3 and parts[2] == "decisions":
                    requires_approval = body.get("requires_approval", False)
                    if not isinstance(requires_approval, bool):
                        raise ValueError("requires_approval must be a JSON boolean")
                    result = service.record_decision(
                        task_id, body.get("choice", ""), body.get("rationale", ""),
                        body.get("supporting_position_ids", []), body.get("considered_not_chosen_position_ids", []),
                        requires_approval, actor=actor,
                    )
                    self._send(201, result)
                    return
                if len(parts) == 3 and parts[2] == "approvals":
                    self._send(201, service.record_approval(
                        task_id, body.get("action", ""), body.get("note", ""), actor=actor,
                        action_name=body.get("action_name", ""), target=body.get("target", ""),
                        scope=body.get("scope", ""), expires_at=body.get("expires_at"),
                    ))
                    return
                if len(parts) == 4 and parts[2:] == ["actions", "authorize"]:
                    self._send(200, service.authorize_action(
                        task_id, body.get("action_name", ""), actor=actor,
                        target=body.get("target", ""), scope=body.get("scope", ""),
                    ))
                    return
                if len(parts) == 3 and parts[2] == "artifacts":
                    self._send(201, service.attach_artifact(
                        task_id, body.get("kind", ""), body.get("uri", ""), body.get("sha256"), actor=actor,
                    ))
                    return
            self._send(404, {"error": "NotFound", "message": "route not found"})
        except Exception as exc:
            self._error(exc)


def serve(service: BridgeService, host: str = "127.0.0.1", port: int = 8000) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("v0 HTTP server is loopback-only; external binding requires an authenticated deployment boundary")
    server = BridgeHTTPServer((host, port), service)
    print(f"Universal AI Bridge v0 listening at http://{host}:{port}")
    print("Manual submissions only; no external AI provider is connected.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Bridge server...")
    finally:
        server.server_close()
