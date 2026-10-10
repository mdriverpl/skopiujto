"""Document activity derived from its status, open deadlines and approval requests."""
from typing import Literal

DocumentStatus = Literal['Szkic', 'W toku', 'Do podpisania', 'Do modyfikacji', 'Do akceptacji', 'Gotowy', 'Archiwum']

def active_actions(status, pending_approvals, deadlines):
    if status == 'Archiwum':
        return []
    labels = {
        'Szkic': ('modification', 'Do modyfikacji'),
        'W toku': ('in_progress', 'W toku'),
        'Do podpisania': ('signature', 'Do podpisania'),
        'Do modyfikacji': ('modification', 'Do modyfikacji'),
        'Do akceptacji': ('approval', 'Do akceptacji'),
    }
    actions = []
    if status in labels:
        kind, label = labels[status]
        actions.append({'kind': kind, 'label': label})
    if pending_approvals:
        existing = next((action for action in actions if action['kind'] == 'approval'), None)
        if existing:
            existing['count'] = pending_approvals
        else:
            actions.append({'kind': 'approval', 'label': 'Oczekuje na akceptację', 'count': pending_approvals})
    open_deadlines = [deadline for deadline in deadlines if not deadline['done']]
    if open_deadlines:
        actions.append({'kind': 'deadline', 'label': 'Otwarty termin', 'count': len(open_deadlines)})
    return actions
