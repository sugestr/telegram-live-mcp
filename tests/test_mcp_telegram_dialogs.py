import asyncio
import time
import unittest
from unittest import mock
from telegram_live_mcp import mcp_telegram

class FakeEntity:
    broadcast = False

    def __init__(self, migrated_to=None):
        self.migrated_to = migrated_to

class FakeDialog:

    def __init__(self, chat_id, name, is_group=True, migrated_to=None):
        self.id = chat_id
        self.name = name
        self.is_group = is_group
        self.entity = FakeEntity(migrated_to=migrated_to)

def _reader(dialogs):
    reader = object.__new__(mcp_telegram.Reader)
    reader.cfg = None
    reader.client = object()
    reader.loop = asyncio.new_event_loop()
    reader._titles = {}
    reader._dialog_cache = None
    reader._dialog_cache_at = 0.0
    reader._dialog_refresh_at = None
    reader._by_id = None
    reader._connect = lambda **kwargs: reader.client
    reader.scans = []
    return reader

class TestDialogCacheRefresh(unittest.TestCase):

    def setUp(self):
        self.account = {-100: FakeDialog(-100, 'Project requests')}
        self.calls = []

        async def collect(_client):
            self.calls.append(1)
            return dict(self.account)
        patcher = mock.patch.object(mcp_telegram.tgfolders, 'get_dialogs_by_id', collect)
        patcher.start()
        self.addCleanup(patcher.stop)
        audit = mock.patch.object(mcp_telegram, '_audit', lambda *a, **k: None)
        audit.start()
        self.addCleanup(audit.stop)
        self.reader = _reader(self.account)
        self.addCleanup(self.reader.loop.close)

    def test_group_created_after_start_is_found_without_restart(self):
        self.assertIn('Project requests', self.reader.find_dialogs('requests'))
        self.assertEqual(len(self.calls), 1)
        self.account[-200] = FakeDialog(-200, 'Project payment routing')
        self.reader._dialog_cache_at -= 30
        answer = self.reader.find_dialogs('routing')
        self.assertIn('-200 | Project payment routing | группа', answer)
        self.assertEqual(len(self.calls), 2, 'пустой ответ обновляет список')

    def test_hit_in_cache_costs_no_extra_full_scan(self):
        self.reader.find_dialogs('requests')
        self.reader._dialog_cache_at -= 30
        self.reader.find_dialogs('requests')
        self.assertEqual(len(self.calls), 1)

    def test_cache_expires_by_time(self):
        self.reader.find_dialogs('requests')
        self.account[-300] = FakeDialog(-300, 'новая тихая группа')
        self.reader._dialog_cache_at -= mcp_telegram.DIALOG_CACHE_TTL_SEC + 1
        self.assertIn('новая тихая группа', self.reader.find_dialogs('тихая'))
        self.assertEqual(len(self.calls), 2)

    def test_empty_answer_names_the_real_cause_not_the_spelling(self):
        self.reader.find_dialogs('requests')
        self.reader._dialog_cache_at -= 30
        after_rescan = self.reader.find_dialogs('routing')
        self.assertNotIn('Название нужно как в Telegram', after_rescan)
        self.assertIn('пересобран', after_rescan)
        self.assertIn('состоит в этом чате', after_rescan)
        self.reader._dialog_cache_at -= 30
        in_cooldown = self.reader.find_dialogs('routing')
        self.assertIn('не чаще раза в минуту', in_cooldown)
        self.assertIn('refresh=true', in_cooldown)

    def test_explicit_refresh_rescans_before_the_search(self):
        self.reader.find_dialogs('requests')
        self.calls.clear()
        self.account[-200] = FakeDialog(-200, 'Project payment routing')
        answer = self.reader.find_dialogs('routing', refresh=True)
        self.assertIn('-200 | Project payment routing | группа', answer)
        self.assertEqual(len(self.calls), 1)

    def test_repeated_miss_does_not_rescan_on_every_call(self):
        self.reader.find_dialogs('requests')
        self.calls.clear()
        self.reader.find_dialogs('несуществующая')
        self.assertEqual(self.calls, [])
        self.reader._dialog_cache_at -= 30
        self.reader.find_dialogs('несуществующая')
        self.assertEqual(len(self.calls), 1)
        for _ in range(5):
            self.reader._dialog_cache_at -= 30
            self.reader.find_dialogs('несуществующая')
        self.assertEqual(len(self.calls), 1, 'шторм полных обходов запрещён')

    def test_new_group_is_found_again_after_the_cooldown(self):
        self.reader.find_dialogs('requests')
        self.reader._dialog_cache_at -= 30
        self.reader.find_dialogs('несуществующая')
        self.calls.clear()
        self.account[-400] = FakeDialog(-400, 'ещё одна новая группа')
        self.reader._dialog_cache_at -= 30
        self.reader._dialog_refresh_at -= mcp_telegram.DIALOG_REFRESH_COOLDOWN_SEC + 1
        self.assertIn('ещё одна новая группа', self.reader.find_dialogs('ещё одна'))
        self.assertEqual(len(self.calls), 1)

    def test_migrated_group_is_one_room_and_current_id_is_first(self):
        current_id = -1000000000123
        old_id = -456
        self.account.clear()
        self.account[old_id] = FakeDialog(old_id, 'Project requests', migrated_to=mcp_telegram.types.InputChannel(channel_id=123, access_hash=0))
        self.account[current_id] = FakeDialog(current_id, 'Project requests')
        answer = self.reader.find_dialogs('requests')
        lines = answer.splitlines()
        self.assertTrue(lines[0].startswith(str(current_id)))
        self.assertIn('текущая супергруппа', lines[0])
        self.assertIn('старый id этой группы', lines[1])
        self.assertIn('это одна группа', lines[2])
        self.assertIn(str(current_id), lines[2])

    def test_same_title_without_migration_metadata_is_not_merged(self):
        self.account.clear()
        self.account[-101] = FakeDialog(-101, 'Одинаковое имя')
        self.account[-202] = FakeDialog(-202, 'Одинаковое имя')
        answer = self.reader.find_dialogs('одинаковое')
        self.assertIn('-101 | Одинаковое имя | группа', answer)
        self.assertIn('-202 | Одинаковое имя | группа', answer)
        self.assertNotIn('это одна группа', answer)

    def test_slow_refresh_is_bounded_preserves_cache_and_resumes(self):
        self.reader.find_dialogs('requests')
        old_cache = self.reader._dialog_cache
        old_by_id = self.reader._by_id
        self.reader._dialog_cache_at -= 30
        ready = asyncio.Event()
        calls = []

        async def slow_collect(_client):
            calls.append(1)
            await ready.wait()
            return {-200: FakeDialog(-200, 'новая группа')}
        with mock.patch.object(mcp_telegram, 'DIALOG_LOOKUP_TIMEOUT_SEC', 0.01), mock.patch.object(mcp_telegram.tgfolders, 'get_dialogs_by_id', slow_collect):
            started = time.monotonic()
            result = self.reader.find_dialogs('новая')
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertIn('не завершено', result)
            self.assertNotIn('Ничего не нашлось', result)
            self.assertIs(self.reader._dialog_cache, old_cache)
            self.assertIs(self.reader._by_id, old_by_id)
            task = self.reader._dialog_refresh_task
            self.assertIn('requests', self.reader.find_dialogs('requests'))
            self.assertIs(self.reader._dialog_refresh_task, task)
            self.assertIn('не завершено', self.reader.find_dialogs('новая'))
            ready.set()
            self.assertIn('-200 | новая группа', self.reader.find_dialogs('новая'))
            self.assertEqual(calls, [1])
            self.assertIsNone(self.reader._dialog_refresh_task)

    def test_cold_or_expired_or_explicit_refresh_is_bounded(self):
        for mode in ('cold', 'expired', 'explicit'):
            with self.subTest(mode=mode):
                if mode != 'cold':
                    self.reader.find_dialogs('requests')
                    self.reader._dialog_cache_at -= mcp_telegram.DIALOG_CACHE_TTL_SEC + 1

                async def stalled(_client):
                    await asyncio.Event().wait()
                with mock.patch.object(mcp_telegram, 'DIALOG_LOOKUP_TIMEOUT_SEC', 0.01), mock.patch.object(mcp_telegram.tgfolders, 'get_dialogs_by_id', stalled):
                    result = self.reader.find_dialogs('requests', refresh=mode == 'explicit')
                    self.assertIn('не завершено', result)
                    if mode != 'cold':
                        self.assertIn('Project requests', result)
                    task = self.reader._dialog_refresh_task
                    task.cancel()
                    self.reader.loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
                    self.reader._dialog_refresh_task = None

    def test_refresh_error_can_be_retried(self):
        with mock.patch.object(mcp_telegram.tgfolders, 'get_dialogs_by_id', side_effect=RuntimeError('network unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'network unavailable'):
                self.reader.find_dialogs('requests')
        self.assertIsNone(self.reader._dialog_refresh_task)
        self.assertIn('requests', self.reader.find_dialogs('requests'))

    def test_cold_connection_is_inside_the_lookup_budget(self):
        self.reader.client = None
        self.reader.cfg = {'api_id': 1, 'api_hash': 'test-placeholder'}
        self.reader._connect = mcp_telegram.Reader._connect.__get__(self.reader)
        self.reader._session_path = lambda : 'unused-test-session'
        client = mock.Mock()
        client.connect = mock.AsyncMock(side_effect=lambda : None)

        async def stalled():
            await asyncio.Event().wait()
        client.is_user_authorized = stalled
        with mock.patch.dict(mcp_telegram.os.environ, {'TG_API_ID': '1', 'TG_API_HASH': 'fake'}), mock.patch.object(mcp_telegram, 'TelegramClient', return_value=client), mock.patch.object(mcp_telegram.readonly, 'lock') as lock, mock.patch.object(mcp_telegram, 'DIALOG_LOOKUP_TIMEOUT_SEC', 0.01):
            started = time.monotonic()
            self.assertIn('не завершено', self.reader.find_dialogs('requests'))
            self.assertLess(time.monotonic() - started, 0.5)
        lock.assert_called_once_with(client)
        self.assertIsNone(self.reader.client)

    def test_audit_failure_stops_lookup_before_network(self):
        with mock.patch.object(mcp_telegram, '_audit', side_effect=OSError('audit unavailable')):
            with self.assertRaises(OSError):
                self.reader.find_dialogs('requests')
        self.assertEqual(self.calls, [])
if __name__ == '__main__':
    unittest.main()
