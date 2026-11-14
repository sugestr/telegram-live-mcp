import asyncio
import unittest
from unittest import mock
from telegram_live_mcp import mcp_telegram
from tests.test_mcp_telegram_dialogs import FakeDialog, _reader

def _folder(fid, title, chat_ids, by_rule=(), groups=False):
    flags = {flag: False for flag in mcp_telegram.tgfolders.FILTER_FLAGS}
    flags['groups'] = groups
    return {'id': fid, 'title': title, 'type': 'DialogFilter', 'chat_ids': sorted(chat_ids), 'explicit_ids': sorted(set(chat_ids) - set(by_rule)), 'by_rule': sorted(by_rule), 'missing_from_dialogs': [], 'flags': flags}

class TestListFolders(unittest.TestCase):

    def setUp(self):
        self.account = {-101: FakeDialog(-101, 'Demo Paris'), -102: FakeDialog(-102, 'Demo BCN'), -103: FakeDialog(-103, 'Бухгалтерия')}
        self.folders = [_folder(2, 'Директора', [-101, -102]), _folder(5, 'Фин учет', [-103, -102], by_rule=[-103], groups=True), _folder(7, 'Директора старые', [-101])]
        self.events = []

        async def collect(_client):
            self.events.append('network')
            return dict(self.account)

        async def get_folders(_client, by_id, for_collection=False):
            self.events.append(('folders', for_collection, len(by_id)))
            return list(self.folders)
        for (name, fake) in (('get_dialogs_by_id', collect), ('get_folders', get_folders)):
            patcher = mock.patch.object(mcp_telegram.tgfolders, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        audit = mock.patch.object(mcp_telegram, '_audit', lambda _cfg, action, detail: self.events.append((action, detail)))
        audit.start()
        self.addCleanup(audit.stop)
        self.reader = _reader(self.account)
        self.addCleanup(self.reader.loop.close)

    def test_without_folder_lists_folders_with_counts_and_rules(self):
        answer = self.reader.list_folders()
        self.assertIn('2 | Директора | чатов 2 (явно 2, по правилам 0)', answer)
        self.assertIn('5 | Фин учет | чатов 2 (явно 1, по правилам 1) | правила: группы', answer)
        self.assertNotIn('Demo Paris', answer)

    def test_counts_add_up_after_folder_exclusions(self):
        excluded = _folder(9, 'Без исключённых', [-101], by_rule=[-101, -102, -103], groups=True)
        self.folders.append(excluded)
        answer = self.reader.list_folders()
        self.assertIn('9 | Без исключённых | чатов 1 (явно 0, по правилам 1)', answer)

    def test_composition_uses_collection_semantics(self):
        self.reader.list_folders('директора')
        self.assertIn(('folders', True, 3), self.events)

    def test_folder_by_title_or_id_returns_its_chats(self):
        by_title = self.reader.list_folders('Директора')
        self.assertIn('Папка «Директора» (id 2): чатов 2', by_title)
        self.assertIn('-102 | Demo BCN | группа', by_title)
        self.assertIn('-101 | Demo Paris | группа', by_title)
        self.assertNotIn('Бухгалтерия', by_title)
        by_id = self.reader.list_folders('5')
        self.assertIn('-103 | Бухгалтерия | группа | по правилу', by_id)

    def test_unknown_and_ambiguous_folder_name_the_choices(self):
        self.assertIn('Папки «Нет такой» нет. Есть:', self.reader.list_folders('Нет такой'))
        ambiguous = self.reader.list_folders('дир')
        self.assertIn('несколько папок', ambiguous)
        self.assertIn('«Директора старые» (id 7)', ambiguous)

    def test_limit_cuts_and_names_the_rest(self):
        answer = self.reader.list_folders('Директора', limit=1)
        self.assertIn('показаны первые 1', answer)
        self.assertEqual(answer.count(' | группа'), 1)

    def test_every_call_is_journalled_before_the_network(self):
        self.reader.list_folders('Фин учет')
        first_audit = self.events.index(('list_folders', '«Фин учет»: запрошено'))
        self.assertLess(first_audit, self.events.index('network'))
        self.assertIn(('list_folders', '«Фин учет»: отдано 2 из 2'), self.events)

    def test_tool_is_declared_for_the_server(self):
        names = [tool['name'] for tool in mcp_telegram.TOOLS]
        self.assertIn('list_folders', names)
        self.assertIn('folders', mcp_telegram.SERVER_INSTRUCTIONS)
if __name__ == '__main__':
    unittest.main()
