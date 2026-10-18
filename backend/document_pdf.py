"""PDF export of the validated rich-text document, with embedded Polish fonts."""
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable


@lru_cache(maxsize=1)
def register_fonts():
    directories = [Path('/usr/share/fonts/truetype/dejavu'), Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts']
    for directory in directories:
        names = (['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans-Oblique.ttf', 'DejaVuSans-BoldOblique.ttf']
                 if (directory / 'DejaVuSans.ttf').exists() else ['arial.ttf', 'arialbd.ttf', 'ariali.ttf', 'arialbi.ttf'])
        if all((directory / name).exists() for name in names):
            for suffix, filename in zip(('', '-Bold', '-Italic', '-BoldItalic'), names):
                pdfmetrics.registerFont(TTFont('Document' + suffix, str(directory / filename)))
            pdfmetrics.registerFontFamily('Document', normal='Document', bold='Document-Bold', italic='Document-Italic', boldItalic='Document-BoldItalic')
            return
    raise RuntimeError('Brak czcionki PDF. Zainstaluj fonts-dejavu-core.')


def inline(node):
    kind = node['type']
    if kind == 'hardBreak':
        return '<br/>'
    if kind != 'text':
        return ''.join(inline(child) for child in node.get('content', []))
    text = escape(node['text']).replace('\n', '<br/>')
    for mark in node.get('marks', []):
        tag = {'bold': 'b', 'italic': 'i', 'underline': 'u', 'strike': 'strike'}.get(mark['type'])
        if tag:
            text = f'<{tag}>{text}</{tag}>'
        elif mark['type'] == 'textStyle':
            attrs = mark.get('attrs', {})
            settings = []
            if attrs.get('color'):
                settings.append(f'color="{escape(attrs["color"], quote=True)}"')
            if attrs.get('fontSize'):
                size = attrs['fontSize']
                points = float(size[:-2]) * (0.75 if size.endswith('px') else 1)
                settings.append(f'size="{points}"')
            if settings:
                text = '<font ' + ' '.join(settings) + '>' + text + '</font>'
    return text


def render_pdf(document):
    register_fonts()
    output = BytesIO()
    pdf = SimpleDocTemplate(output, pagesize=A4, title=document['title'],
                           leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
    story = []
    def blocks(nodes, indent=0, bullet=None):
        for index, node in enumerate(nodes):
            kind = node['type']
            attrs = node.get('attrs', {})
            if kind in ('paragraph', 'heading'):
                size = {1: 22, 2: 17, 3: 14}.get(attrs.get('level'), 11) if kind == 'heading' else 11
                style = ParagraphStyle('document', fontName='Document-Bold' if kind == 'heading' else 'Document',
                    fontSize=size, leading=size * 1.45, autoLeading='max', spaceAfter=9, leftIndent=indent,
                    bulletFontName='Document', bulletIndent=max(0, indent - 14),
                    alignment={'left': TA_LEFT, 'center': TA_CENTER, 'right': TA_RIGHT, 'justify': TA_JUSTIFY}.get(attrs.get('textAlign'), TA_LEFT))
                story.append(Paragraph(inline(node) or '&#160;', style, bulletText=bullet if index == 0 else None))
            elif kind in ('bulletList', 'orderedList'):
                start = attrs.get('start', 1)
                for number, item in enumerate(node.get('content', []), start):
                    blocks(item.get('content', []), indent + 20, '•' if kind == 'bulletList' else f'{number}.')
            elif kind == 'blockquote':
                blocks(node.get('content', []), indent + 20)
            elif kind == 'horizontalRule':
                story.extend([HRFlowable(width='100%', color=colors.grey), Spacer(1, 9)])
    rich = document.get('rich_content')
    nodes = rich.get('content', []) if rich else [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': line}]} for line in document.get('content', '').split('\n')]
    blocks(nodes)
    if not story:
        story.append(Spacer(1, 1))
    pdf.build(story)
    return output.getvalue()
