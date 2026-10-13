"""Authenticated WebSocket invalidation; no student data or tokens in URLs."""
import asyncio
import contextlib
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from backend.app.core.config import settings
from backend.app.core.database import TargetSessionLocal
from backend.app.core.security import get_current_user
from backend.app.core.time import business_day, local_now
from backend.app.services.change_events import change_marker

router = APIRouter()


def authorized(token):
    with TargetSessionLocal() as db:
        get_current_user(token, db)


def marker():
    with TargetSessionLocal() as db:
        return change_marker(db), business_day(local_now()).isoformat()


class ChangeHub:
    def __init__(self):
        self.queues = set()
        self.task = None

    def subscribe(self):
        queue = asyncio.Queue(maxsize=1)
        self.queues.add(queue)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())
        return queue

    def unsubscribe(self, queue):
        self.queues.discard(queue)
        if not self.queues and self.task:
            self.task.cancel()
            self.task = None

    async def run(self):
        previous = None
        while self.queues:
            try:
                current = await asyncio.to_thread(marker)
                if current != previous:
                    for queue in tuple(self.queues):
                        if queue.empty():
                            queue.put_nowait('refresh')
                    previous = current
            except asyncio.CancelledError:
                raise
            except Exception:
                for queue in tuple(self.queues):
                    if queue.empty():
                        queue.put_nowait('unavailable')
            await asyncio.sleep(1)


hub = ChangeHub()


@router.websocket('/dashboard/live')
async def dashboard_live(socket: WebSocket):
    origin = socket.headers.get('origin')
    if origin and origin not in settings.get_allowed_origins():
        # Same-origin local deployment also allowed, regardless of host name.
        from urllib.parse import urlsplit
        parts = urlsplit(origin)
        if parts.netloc != socket.headers.get('host') or parts.scheme not in ('http', 'https'):
            await socket.close(code=1008)
            return
    await socket.accept()
    queue = None
    receiver = None
    update = None
    try:
        payload = await asyncio.wait_for(socket.receive_text(), timeout=5)
        if len(payload) > 4096:
            raise ValueError('Authentication message too large')
        import json
        token = json.loads(payload).get('token')
        if not isinstance(token, str):
            raise ValueError('Token required')
        await asyncio.to_thread(authorized, token)
        queue = hub.subscribe()
        await socket.send_json({'type': 'ready'})
        # Receive concurrently so disconnects are noticed even on a quiet dashboard.
        receiver = asyncio.create_task(socket.receive())
        while True:
            update = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait((receiver, update), timeout=15, return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                update.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await update
                break
            # Recheck expiry, revocation and warden assignment before every message.
            await asyncio.to_thread(authorized, token)
            if update in done:
                event_type = update.result()
                if event_type == 'unavailable':
                    await socket.close(code=1013)
                    break
                await socket.send_json({'type': 'refresh'})
            else:
                update.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await update
                await socket.send_json({'type': 'heartbeat'})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (HTTPException, ValueError, TypeError, asyncio.TimeoutError):
        await socket.close(code=1008)
    except Exception:
        with contextlib.suppress(RuntimeError):
            await socket.close(code=1013)
    finally:
        if update and not update.done():
            update.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await update
        if receiver:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver
        if queue:
            hub.unsubscribe(queue)
