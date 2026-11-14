from datetime import datetime, timezone
from telethon import functions, types, utils
FLAG_KINDS = {'contacts': 'contact', 'non_contacts': 'non_contact', 'groups': 'group', 'broadcasts': 'broadcast', 'bots': 'bot'}
FILTER_FLAGS = tuple(FLAG_KINDS) + ('exclude_muted', 'exclude_read', 'exclude_archived')

def filter_title(flt):
    title = getattr(flt, 'title', None)
    if title is None:
        return '(без названия)'
    return getattr(title, 'text', title)

def peer_ids(peers):
    out = []
    for peer in peers or []:
        try:
            out.append(utils.get_peer_id(peer))
        except (TypeError, ValueError):
            pass
    return out

def is_muted(dialog):
    settings = getattr(dialog.dialog, 'notify_settings', None)
    if settings is None:
        return False
    if getattr(settings, 'silent', False):
        return True
    mute_until = getattr(settings, 'mute_until', None)
    if mute_until is None:
        return False
    if isinstance(mute_until, datetime):
        return mute_until > datetime.now(timezone.utc)
    return bool(mute_until)

def entity_kind(entity):
    if isinstance(entity, types.User):
        if entity.bot:
            return 'bot'
        return 'contact' if entity.contact else 'non_contact'
    if isinstance(entity, types.Channel) and entity.broadcast:
        return 'broadcast'
    return 'group'

def dialog_kind(dialog):
    return entity_kind(dialog.entity)

async def get_dialogs_by_id(client):
    dialogs = await client.get_dialogs(limit=None, archived=None)
    out = {}
    for d in dialogs:
        try:
            out[utils.get_peer_id(d.input_entity)] = d
        except (TypeError, ValueError):
            out[d.id] = d
    return out

def resolve_filter(flt, dialogs_by_id, for_collection=False):
    explicit = set(peer_ids(getattr(flt, 'pinned_peers', None)))
    explicit |= set(peer_ids(getattr(flt, 'include_peers', None)))
    included = set(explicit)
    wanted = {kind for (attr, kind) in FLAG_KINDS.items() if getattr(flt, attr, False)}
    by_rule = set()
    if wanted:
        for (chat_id, dialog) in dialogs_by_id.items():
            if dialog_kind(dialog) not in wanted:
                continue
            if not for_collection:
                if getattr(flt, 'exclude_muted', False) and is_muted(dialog):
                    continue
                if getattr(flt, 'exclude_read', False) and (not dialog.unread_count):
                    continue
            if getattr(flt, 'exclude_archived', False) and dialog.archived:
                continue
            by_rule.add(chat_id)
    included |= by_rule
    included -= set(peer_ids(getattr(flt, 'exclude_peers', None)))
    included |= explicit
    return (included, explicit, by_rule - explicit)

async def get_folders(client, dialogs_by_id, for_collection=False):
    raw = await client(functions.messages.GetDialogFiltersRequest())
    raw_filters = getattr(raw, 'filters', raw)
    folders = []
    for flt in raw_filters:
        if isinstance(flt, types.DialogFilterDefault):
            continue
        (chat_ids, explicit, by_rule) = resolve_filter(flt, dialogs_by_id, for_collection=for_collection)
        folders.append({'id': getattr(flt, 'id', None), 'title': filter_title(flt), 'type': type(flt).__name__, 'chat_ids': sorted(chat_ids), 'explicit_ids': sorted(explicit), 'by_rule': sorted(by_rule), 'missing_from_dialogs': sorted(chat_ids - set(dialogs_by_id)), 'flags': {k: bool(getattr(flt, k, False)) for k in FILTER_FLAGS}})
    return folders
