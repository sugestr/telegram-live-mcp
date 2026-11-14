import os
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from telethon import types, utils
from telegram_live_mcp import folders

class FakeNotifySettings(object):

    def __init__(self, silent=False, mute_until=None):
        self.silent = silent
        self.mute_until = mute_until

class FakeDialogRaw(object):

    def __init__(self, muted=False):
        self.notify_settings = FakeNotifySettings(silent=muted)

class FakeDialog(object):

    def __init__(self, unread=0, muted=False, archived=False):
        self.entity = object()
        self.dialog = FakeDialogRaw(muted)
        self.unread_count = unread
        self.archived = archived

class FakeFilter(object):

    def __init__(self, title='Папка', **flags):
        self.title = title
        self.id = 2
        self.include_peers = []
        self.pinned_peers = []
        self.exclude_peers = []
        for flag in folders.FILTER_FLAGS:
            setattr(self, flag, flags.get(flag, False))

def peer(channel_id):
    return types.PeerChannel(channel_id=channel_id)

class TestRuleBasedFolders(unittest.TestCase):

    def setUp(self):
        self.chat_id = utils.get_peer_id(peer(555))
        self.dialogs = {self.chat_id: FakeDialog(unread=0)}

    def test_exclude_read_hides_chat_from_display(self):
        flt = FakeFilter(groups=True, exclude_read=True)
        (included, _, _) = folders.resolve_filter(flt, self.dialogs)
        self.assertEqual(included, set())

    def test_exclude_read_is_ignored_for_collection(self):
        flt = FakeFilter(groups=True, exclude_read=True)
        (included, _, _) = folders.resolve_filter(flt, self.dialogs, for_collection=True)
        self.assertEqual(included, {self.chat_id})

    def test_exclude_muted_is_ignored_for_collection(self):
        dialogs = {self.chat_id: FakeDialog(unread=3, muted=True)}
        flt = FakeFilter(groups=True, exclude_muted=True)
        (display, _, _) = folders.resolve_filter(flt, dialogs)
        (collect, _, _) = folders.resolve_filter(flt, dialogs, for_collection=True)
        self.assertEqual(display, set())
        self.assertEqual(collect, {self.chat_id})

    def test_archived_flag_still_applies(self):
        dialogs = {self.chat_id: FakeDialog(unread=1, archived=True)}
        flt = FakeFilter(groups=True, exclude_archived=True)
        (collect, _, _) = folders.resolve_filter(flt, dialogs, for_collection=True)
        self.assertEqual(collect, set())

class TestExplicitPeers(unittest.TestCase):

    def test_explicit_chat_survives_exclusion(self):
        chat_id = utils.get_peer_id(peer(777))
        flt = FakeFilter()
        flt.include_peers = [peer(777)]
        flt.exclude_peers = [peer(777)]
        (included, explicit, by_rule) = folders.resolve_filter(flt, {})
        self.assertEqual(included, {chat_id})
        self.assertEqual(explicit, {chat_id})
        self.assertEqual(by_rule, set())

    def test_rule_based_chat_is_reported_separately(self):
        chat_id = utils.get_peer_id(peer(555))
        flt = FakeFilter(groups=True)
        (_, explicit, by_rule) = folders.resolve_filter(flt, {chat_id: FakeDialog(unread=1)}, for_collection=True)
        self.assertEqual(explicit, set())
        self.assertEqual(by_rule, {chat_id})
if __name__ == '__main__':
    unittest.main(verbosity=2)
