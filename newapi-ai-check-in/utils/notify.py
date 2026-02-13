import os
import json

from typing import Literal

import httpx


class NotificationKit:
    def __init__(self):
        self.notify_type: str = os.getenv('NOTIFY_TYPE', '')
        self.notify_config: str = os.getenv('NOTIFY_CONFIG', '')

    def send_http(self, title: str, content: str):
        if self.notify_config == '':
            return
        try:
            notify_config = json.loads(self.notify_config)
            msg = title + "\n" + content
            data = {'token': notify_config.get('token'), 'tag': 'AnyRouter', 'msg': msg}

            with httpx.Client(timeout=30.0) as client:
                client.post(notify_config.get('url'), json=data)
        except Exception as e:
            print(f"Notification failed: {e}")

    def push_message(self, title: str, content: str, msg_type: Literal['text', 'html'] = 'text'):
        if self.notify_type == 'http' and msg_type == 'text':
            self.send_http(title, content)

notify = NotificationKit()