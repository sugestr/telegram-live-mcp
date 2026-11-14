FORBIDDEN = ('send_message', 'send_file', 'send_read_acknowledge', 'forward_messages', 'edit_message', 'delete_messages', 'pin_message', 'unpin_message', 'join_chat', 'leave_chat', 'kick_participant', 'edit_admin', 'edit_permissions', 'delete_dialog', 'set_profile_photo')

def lock(client, names=FORBIDDEN):

    def make_guard(name):

        def guard(*args, **kwargs):
            raise RuntimeError('процесс строго read-only, вызов %s запрещён' % name)
        return guard
    for name in names:
        if hasattr(client, name):
            setattr(client, name, make_guard(name))
    return client
