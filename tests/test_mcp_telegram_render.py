import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from telethon import types
from telegram_live_mcp import mcp_telegram

def message(sender=None, sender_id=None, **extra):
    return SimpleNamespace(id=91, date=datetime(2026, 10, 15, 12, tzinfo=timezone.utc), message='текст', sender=sender, sender_id=sender_id, out=False, media=None, **extra)

class TestSenderIdentity(unittest.TestCase):

    def setUp(self):
        self.reader = object.__new__(mcp_telegram.Reader)

    def render(self, item):
        return self.reader._render([item], 'чат')

    def test_user_id_username_and_topic_are_rendered_together(self):
        item = message(types.User(id=123, first_name='Анна', username='anna'), 123, reply_to=SimpleNamespace(reply_to_top_id=777, quote_text=None))
        result = self.render(item)
        self.assertIn('[message_id=91; message_thread_id=777; sender_id=123]', result)
        self.assertIn('Анна (@anna): текст', result)

    def test_user_without_username_still_has_mentionable_id(self):
        result = self.render(message(types.User(id=456, first_name='Анна'), 456))
        self.assertIn('sender_id=456', result)
        self.assertIn('Анна: текст', result)
        self.assertNotIn('(@', result)

    def test_unresolved_sender_keeps_the_message_id_of_the_sender(self):
        self.assertIn('sender_id=789', self.render(message(sender_id=789)))

    def test_sender_entity_is_a_fallback_for_missing_sender_id(self):
        self.assertIn('sender_id=123', self.render(message(types.User(id=123))))

    def test_channel_or_anonymous_admin_uses_marked_channel_id(self):
        channel = types.Channel(id=1234, title='Канал', photo=types.ChatPhotoEmpty(), date=datetime.now(timezone.utc))
        result = self.render(message(channel, post_author='Подпись'))
        self.assertIn('sender_id=-1000000001234', result)
        self.assertNotIn('sender_id=1234', result)

    def test_signature_without_sender_does_not_invent_identity(self):
        result = self.render(message(post_author='Подпись'))
        self.assertIn('Подпись: текст', result)
        self.assertNotIn('sender_id=', result)
        self.assertNotIn('(@', result)

    def test_read_and_search_both_expose_sender_identity(self):
        item = message(types.User(id=123, first_name='Анна', username='anna'), 123)

        async def iter_messages(*args, **kwargs):
            yield item
        self.reader.cfg = None
        self.reader.loop = asyncio.new_event_loop()
        self.addCleanup(self.reader.loop.close)
        self.reader._connect = lambda : SimpleNamespace(iter_messages=iter_messages)
        self.reader._title_of = lambda chat_id: 'чат'
        with patch.object(mcp_telegram, '_audit'):
            results = [self.reader.read_chat(-100, since='2026-10-14', until='2026-10-16'), self.reader.search_chat(-100, 'текст')]
        for result in results:
            self.assertIn('sender_id=123', result)
            self.assertIn('Анна (@anna): текст', result)
