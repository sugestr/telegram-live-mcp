import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from telegram_live_mcp import auth, cli, config, mcp_telegram, readonly, voice_cache


class Standalone(unittest.TestCase):
    def test_no_write_methods(self):
        client = SimpleNamespace(**{name: Mock() for name in readonly.FORBIDDEN})
        readonly.lock(client)
        for name in readonly.FORBIDDEN:
            with self.assertRaisesRegex(RuntimeError, 'read-only'):
                getattr(client, name)('anything')
        self.assertEqual({x['name'] for x in mcp_telegram.TOOLS}, {
            'find_dialogs', 'list_folders', 'read_chat', 'search_chat',
            'get_forum_topic', 'get_media', 'export_text'})

    def test_audit_failure_prevents_first_connection_for_all_reads(self):
        reader = object.__new__(mcp_telegram.Reader)
        reader.cfg = {}
        reader._connect = Mock(side_effect=AssertionError('network attempted'))
        for name, args in [('find_dialogs', ['demo']), ('list_folders', []),
                           ('read_chat', [123]), ('search_chat', [123, 'demo']),
                           ('get_forum_topic', [123, 45]), ('get_media', [123, 45]),
                           ('export_text', [123, [45]])]:
            with self.subTest(name=name), patch.object(mcp_telegram, '_audit', side_effect=OSError('audit')):
                with self.assertRaises(OSError):
                    getattr(reader, name)(*args)
        reader._connect.assert_not_called()

    def test_private_state_and_transcript(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'TELEGRAM_LIVE_HOME': root}):
            path = Path(root)/'credentials.json'
            path.write_text(json.dumps({'api_id': 1, 'api_hash': 'a'*32}))
            cfg = config.load()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(cfg['run_dir']).stat().st_mode & 0o777, 0o700)
            self.assertTrue(voice_cache.put(123, 45, 'synthetic transcript', root=Path(root)/'transcripts'))
            self.assertEqual((Path(root)/'transcripts/123/45.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(voice_cache.get(123,45,root=Path(root)/'transcripts'), 'synthetic transcript')

    def test_discovery_without_login_and_error_is_recoverable(self):
        with tempfile.TemporaryDirectory() as root:
            env = dict(os.environ, TELEGRAM_LIVE_HOME=root)
            reqs = [
                {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},
                {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'find_dialogs','arguments':{'query':'demo'}}},
                {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'send_message','arguments':{}}},
                {'jsonrpc':'2.0','id':5,'method':'ping'},
            ]
            result = subprocess.run([str(Path(sys.executable).with_name('telegram-live')), 'serve'],
                                    input='\n'.join(json.dumps(x) for x in reqs)+'\n',
                                    capture_output=True,text=True,env=env,timeout=10,check=True)
            data = [json.loads(x) for x in result.stdout.splitlines()]
            self.assertEqual(len(data),5)
            self.assertEqual(len(data[1]['result']['tools']),7)
            self.assertTrue(data[2]['result']['isError'])
            self.assertEqual(data[3]['error']['code'],-32601)
            self.assertEqual(data[4]['result'],{})
            self.assertFalse(list(Path(root).glob('*.session')))

    def test_foreign_host_session_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'account.session';path.write_bytes(b'not a real session')
            auth.session_host_file(path).write_text('not-this-host')
            reader=object.__new__(mcp_telegram.Reader)
            reader.cfg={'session_path':str(path),'run_dir':str(Path(root)/'run')}
            with self.assertRaisesRegex(RuntimeError,'другой хост'):
                reader._session_path()
            self.assertFalse((Path(root)/'run').exists())

    def test_existing_codex_server_is_not_overwritten(self):
        with patch.object(cli,'codex_binary',return_value='codex'), patch.object(cli,'executable',return_value=Path(sys.executable)), patch.object(cli.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            with self.assertRaisesRegex(SystemExit,'уже зарегистрирован'):
                cli.register_codex()
            self.assertEqual(run.call_count,1)

    def test_login_refuses_noninteractive_input(self):
        import asyncio
        with patch.object(sys.stdin,'isatty',return_value=False):
            with self.assertRaisesRegex(SystemExit,'Терминале'):
                asyncio.run(cli.login())
