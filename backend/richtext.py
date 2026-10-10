"""A bounded, explicit document schema; no raw HTML or arbitrary CSS is stored."""
import json
import re

from fastapi import HTTPException

FONTS = {'Inter', 'Arial', 'Calibri', 'Georgia', 'Times New Roman', 'Verdana', 'Courier New'}
BLOCKS = {'paragraph', 'heading', 'bulletList', 'orderedList', 'blockquote', 'horizontalRule'}
INLINE = {'text', 'hardBreak'}
MARKS = {'bold', 'italic', 'underline', 'strike', 'textStyle'}

def validate(value):
    if value is None:
        return None
    count = 0
    text_length = 0
    def reject():
        raise HTTPException(422, 'Nieobsługiwane formatowanie tekstu. Użyj narzędzi dostępnych w edytorze.')
    def attributes(attrs, kind):
        if not isinstance(attrs, dict): reject()
        attrs = {key: val for key, val in attrs.items() if val is not None}
        allowed = {'heading': {'level', 'textAlign'}, 'paragraph': {'textAlign'}, 'orderedList': {'start', 'type'},
                   'textStyle': {'fontFamily', 'fontSize', 'color'}}.get(kind, set())
        if set(attrs) - allowed: reject()
        for key, val in attrs.items():
            if key == 'level' and (type(val) is not int or val not in (1, 2, 3)): reject()
            if key == 'start' and (type(val) is not int or not 1 <= val <= 100000): reject()
            if key == 'type' and val not in ('1', 'a', 'A', 'i', 'I'): reject()
            if key == 'textAlign' and val not in ('left', 'center', 'right', 'justify'): reject()
            if key == 'fontFamily' and (not isinstance(val, str) or val not in FONTS): reject()
            if key == 'fontSize':
                if not isinstance(val, str) or not re.fullmatch(r'\d+(?:\.\d+)?(?:px|pt)', val) or not 8 <= float(val[:-2]) <= 72: reject()
            if key == 'color':
                if not isinstance(val, str): reject()
                rgb = re.fullmatch(r'rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)', val)
                if not (re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', val) or (rgb and all(int(part) <= 255 for part in rgb.groups()))): reject()
        return attrs
    def visit(node, parent=None, depth=0):
        nonlocal count, text_length
        count += 1
        if count > 20000 or depth > 30:
            raise HTTPException(413, 'Tekst jest zbyt rozbudowany. Limit to 20 000 elementów i 30 poziomów zagnieżdżenia.')
        if not isinstance(node, dict) or set(node) - {'type', 'attrs', 'content', 'marks', 'text'}: reject()
        kind = node.get('type')
        children = node.get('content', [])
        if not isinstance(kind, str) or kind not in BLOCKS | INLINE | {'doc', 'listItem'} or not isinstance(children, list): reject()
        expected = {'doc': BLOCKS, 'paragraph': INLINE, 'heading': INLINE, 'blockquote': BLOCKS,
                    'bulletList': {'listItem'}, 'orderedList': {'listItem'}, 'listItem': BLOCKS}.get(parent, set())
        if parent is None and kind != 'doc': reject()
        if parent is not None and kind not in expected: reject()
        if kind in INLINE | {'horizontalRule'} and children: reject()
        if kind in {'doc', 'bulletList', 'orderedList', 'blockquote', 'listItem'} and not children: reject()
        if kind == 'listItem' and (not isinstance(children[0], dict) or children[0].get('type') != 'paragraph'): reject()
        result = {'type': kind}
        attrs = attributes(node.get('attrs', {}), kind)
        if attrs: result['attrs'] = attrs
        if kind == 'text':
            text = node.get('text')
            if not isinstance(text, str) or not text: reject()
            text_length += len(text)
            if text_length > 500000: raise HTTPException(413, 'Maksymalna długość tekstu to 500 000 znaków.')
            result['text'] = text
        elif 'text' in node: reject()
        if 'marks' in node:
            marks = node['marks']
            if kind != 'text' or not isinstance(marks, list) or len(marks) > 5: reject()
            result['marks'] = []
            for mark in marks:
                if not isinstance(mark, dict) or set(mark) - {'type', 'attrs'} or not isinstance(mark.get('type'), str) or mark.get('type') not in MARKS: reject()
                checked = {'type': mark['type']}
                attrs = attributes(mark.get('attrs', {}), mark['type'])
                if attrs: checked['attrs'] = attrs
                result['marks'].append(checked)
        if children: result['content'] = [visit(child, kind, depth + 1) for child in children]
        return result
    checked = visit(value)
    if len(json.dumps(checked, ensure_ascii=False)) > 1500000:
        raise HTTPException(413, 'Formatowany tekst przekracza maksymalny rozmiar.')
    return checked

def plain_text(value):
    def text(node):
        kind = node['type']
        if kind == 'text': return node['text']
        if kind == 'hardBreak': return '\n'
        parts = [text(child) for child in node.get('content', [])]
        return ('' if kind in {'paragraph', 'heading'} else '\n').join(parts)
    return text(value)

def fields(content, rich_content):
    checked = validate(rich_content)
    if checked is None:
        return content, None
    text = plain_text(checked)
    if len(text) > 500000:
        raise HTTPException(413, 'Maksymalna długość tekstu to 500 000 znaków.')
    return text, json.dumps(checked, ensure_ascii=False)

def decode(row):
    result = dict(row)
    result['rich_content'] = json.loads(result['rich_content']) if result.get('rich_content') else None
    return result
