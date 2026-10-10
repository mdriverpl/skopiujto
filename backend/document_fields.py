"""Render document placeholders as plain text while retaining rich-text marks."""
import json
import re

from fastapi import HTTPException
from backend import richtext

PATTERN = re.compile(r'\[([^\[\]\r\n]{1,120})\]')


def key(label):
    return ' '.join(label.split()).lower()


def render(source, values):
    def visit(node):
        if 'content' not in node:
            return dict(node)
        if node['type'] not in ('paragraph', 'heading'):
            return {**node, 'content': [visit(child) for child in node['content']]}
        runs, output, offset = [], [], 0
        for child in node['content']:
            text = '\n' if child['type'] == 'hardBreak' else child.get('text', '')
            runs.append((child, offset, offset + len(text)))
            offset += len(text)
        text = ''.join('\n' if child['type'] == 'hardBreak' else child.get('text', '') for child in node['content'])
        def copy(start, end):
            for child, a, b in runs:
                left, right = max(start, a), min(end, b)
                if left < right:
                    output.append(dict(child) if child['type'] == 'hardBreak' else
                                  {**child, 'text': child['text'][left - a:right - a]})
        cursor = 0
        for match in PATTERN.finditer(text):
            value = values.get(key(match[1]))
            if not value or not value.strip(): continue
            copy(cursor, match.start())
            original = next(child for child, a, b in runs if a <= match.start() < b)
            output.append({**original, 'type': 'text', 'text': value})
            cursor = match.end()
        copy(cursor, len(text))
        result = {**node, 'content': output}
        if not output: result.pop('content')
        return result
    return visit(source)


def prepare(content, formatted, source, values):
    if source is None:
        if values: raise HTTPException(422, 'Dane pól wymagają treści wzoru dokumentu.')
        text, rich = richtext.fields(content, formatted)
        return text, rich, None, '{}'
    checked = richtext.validate(source)
    known = {key(match[1]) for match in PATTERN.finditer(richtext.plain_text(checked)) if key(match[1])}
    if len(known) > 200 or len(values) > 200:
        raise HTTPException(413, 'Dokument może mieć maksymalnie 200 pól do wypełnienia.')
    if set(values) - known or any(not isinstance(value, str) or len(value) > 2000 for value in values.values()):
        raise HTTPException(422, 'Niepoprawne dane pól dokumentu. Maksymalna długość wartości to 2000 znaków.')
    text, rich = richtext.fields('', render(checked, values))
    return text, rich, json.dumps(checked, ensure_ascii=False), json.dumps(values, ensure_ascii=False)


def decode(row):
    result = richtext.decode(row)
    result['field_source'] = json.loads(result['field_source']) if result.get('field_source') else None
    result['field_values'] = json.loads(result['field_values']) if result.get('field_values') else {}
    return result
