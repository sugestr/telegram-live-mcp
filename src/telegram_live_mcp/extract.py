import json
from telethon import types, utils

def _document_card(doc):
    card = {'document_id': getattr(doc, 'id', None), 'access_hash': getattr(doc, 'access_hash', None), 'mime': getattr(doc, 'mime_type', None), 'size': getattr(doc, 'size', None)}
    kind = 'document'
    for attr in getattr(doc, 'attributes', None) or []:
        if isinstance(attr, types.DocumentAttributeFilename):
            card['file_name'] = attr.file_name
        elif isinstance(attr, types.DocumentAttributeAudio):
            kind = 'voice' if getattr(attr, 'voice', False) else 'audio'
            card['duration'] = getattr(attr, 'duration', None)
        elif isinstance(attr, types.DocumentAttributeVideo):
            kind = 'video'
            card['duration'] = getattr(attr, 'duration', None)
        elif isinstance(attr, types.DocumentAttributeSticker):
            kind = 'sticker'
            card['alt'] = getattr(attr, 'alt', None)
    return (kind, card)

def _rich_inline(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    texts = getattr(value, 'texts', None)
    if isinstance(texts, list):
        return ''.join((_rich_inline(item) for item in texts))
    inner = getattr(value, 'text', None)
    if inner is not None and inner is not value:
        return _rich_inline(inner)
    return ''

def _rich_blocks(blocks, prefix=''):
    lines = []
    for block in blocks or ():
        name = type(block).__name__
        if name == 'PageBlockTable':
            title = _rich_inline(getattr(block, 'title', None)).strip()
            if title:
                lines.append(prefix + title)
            for row in getattr(block, 'rows', None) or ():
                cells = [' '.join(_rich_inline(getattr(cell, 'text', None)).split()) for cell in getattr(row, 'cells', None) or ()]
                lines.append(prefix + '| ' + ' | '.join(cells) + ' |')
        elif name in ('PageBlockList', 'PageBlockOrderedList'):
            for (number, item) in enumerate(getattr(block, 'items', None) or (), 1):
                mark = '%s. ' % (getattr(item, 'num', None) or number) if name == 'PageBlockOrderedList' else '• '
                if getattr(item, 'blocks', None):
                    nested = _rich_blocks(item.blocks)
                    if nested:
                        lines.append(prefix + mark + nested[0])
                        lines.extend((prefix + '  ' + line for line in nested[1:]))
                else:
                    lines.append(prefix + mark + _rich_inline(getattr(item, 'text', None)).strip())
        elif name in ('PageBlockBlockquote', 'PageBlockPullquote'):
            for line in _rich_inline(getattr(block, 'text', None)).splitlines():
                lines.append(prefix + '> ' + line)
        elif name == 'PageBlockDetails':
            lines.append(prefix + _rich_inline(getattr(block, 'title', None)).strip())
            lines.extend(_rich_blocks(getattr(block, 'blocks', None), prefix + '>> '))
        elif name == 'PageBlockDivider':
            lines.append(prefix + '—')
        elif getattr(block, 'blocks', None):
            lines.extend(_rich_blocks(block.blocks, prefix))
        else:
            text = _rich_inline(getattr(block, 'text', None))
            lines.extend((prefix + line for line in text.splitlines()))
    return lines

def rich_text(msg):
    rich = getattr(msg, 'rich_message', None)
    if rich is None:
        return ''
    lines = _rich_blocks(getattr(rich, 'blocks', None))
    text = '\n'.join((line.replace('\u200b', '').rstrip() for line in lines))
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    return text.strip()

def media_card(msg):
    media = getattr(msg, 'media', None)
    if media is None:
        return (None, None)
    if isinstance(media, types.MessageMediaDocument):
        doc = getattr(media, 'document', None)
        if doc is None:
            return ('document', None)
        return _document_card(doc)
    if isinstance(media, types.MessageMediaPhoto):
        photo = getattr(media, 'photo', None)
        return ('photo', {'photo_id': getattr(photo, 'id', None), 'access_hash': getattr(photo, 'access_hash', None)})
    if isinstance(media, types.MessageMediaPoll):
        poll = getattr(media, 'poll', None)
        results = getattr(media, 'results', None)
        card = {'question': _poll_text(getattr(poll, 'question', None)), 'options': [_poll_text(getattr(a, 'text', None)) for a in getattr(poll, 'answers', None) or []]}
        votes = getattr(results, 'results', None) or []
        if votes:
            card['votes'] = [getattr(v, 'voters', 0) for v in votes]
        return ('poll', card)
    if isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
        geo = getattr(media, 'geo', None)
        return ('geo', {'lat': getattr(geo, 'lat', None), 'long': getattr(geo, 'long', None)})
    if isinstance(media, types.MessageMediaContact):
        return ('contact', {'phone': getattr(media, 'phone_number', None), 'name': ' '.join(filter(None, [getattr(media, 'first_name', None), getattr(media, 'last_name', None)]))})
    if isinstance(media, types.MessageMediaWebPage):
        page = getattr(media, 'webpage', None)
        return ('webpage', {'url': getattr(page, 'url', None), 'title': getattr(page, 'title', None)})
    return (type(media).__name__.replace('MessageMedia', '').lower(), None)

def _poll_text(value):
    if value is None:
        return None
    return getattr(value, 'text', value)

def display_name(entity):
    if entity is None:
        return None
    try:
        return utils.get_display_name(entity) or None
    except (TypeError, AttributeError):
        return None
