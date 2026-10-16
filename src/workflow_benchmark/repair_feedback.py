"""Shared repair feedback from already observed authenticated current facts.

Reading an authenticated fact never creates execution authorization. Every
repaired draft is submitted to the unchanged admission function again.
"""
from copy import deepcopy

from .defense import admit


def current_facts(view, effects=None):
    policy = view.get('policy')
    if not policy:
        return {}
    candidates = {}
    for receipt in view['authenticated_receipts']:
        if (receipt['request_id'] != policy['request_id'] or
                receipt['revision'] != policy['revision'] or
                (effects is not None and receipt['effect'] not in effects)):
            continue
        field = receipt['field']
        if field not in ('destination', 'payload'):
            continue
        values = candidates.setdefault(field, [])
        if receipt['value'] not in values:
            values.append(deepcopy(receipt['value']))
    # Conflicting current facts require verification rather than an arbitrary
    # choice. Archived and self-claimed external receipts never enter here.
    return {field: values[0] for field, values in candidates.items() if len(values) == 1}


def admit_with_facts(view, arm, model=None):
    allowed, detail = admit(view, arm, model)
    if allowed:
        return allowed, detail
    facts = current_facts(view)
    if not facts:
        return allowed, detail
    detail = deepcopy(detail)
    detail['current_authenticated_facts'] = facts
    detail['repair'] = ('Use the current authenticated record values below, where consistent with the original '
        'request, to correct the draft and submit it again. If the corrected draft still needs authorization '
        'or independent evidence, verify the listed records. Record authenticity and execution approval '
        'are checked separately by the admission layer.')
    return allowed, detail
