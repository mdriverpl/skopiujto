"""Public, stateless demonstration quotes, calculated from the shared price catalog."""
import json
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from backend.document_pdf import register_fonts

CATALOG = json.loads(Path(__file__).with_name('pricing_catalog.json').read_text(encoding='utf-8'))
Plan = Literal['S1', 'S2', 'S4', 'S8', 'S16', 'S32']
router = APIRouter()


class OfferConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    users: int = Field(ge=1, le=500)
    storage: int = Field(ge=100, le=10000)
    server_plan: Plan
    server_ha: bool = False
    database_plan: Literal['none', 'S1', 'S2', 'S4', 'S8', 'S16', 'S32'] = 'none'
    database_engine: Literal['PostgreSQL', 'MySQL', 'MariaDB', 'Redis'] = 'PostgreSQL'
    database_ha: bool = False
    waf: bool = False
    backup: bool = False
    logs: bool = False
    vpn: bool = False

    @field_validator('storage')
    @classmethod
    def storage_increment(cls, value):
        if value % 100:
            raise ValueError('Pojemność musi być wielokrotnością 100 GB.')
        return value


def amount(value):
    return Decimal(str(value))


def money(value):
    return f'{amount(value):,.2f}'.replace(',', ' ').replace('.', ',') + ' zł'


def quote_rows(config):
    rows = [('SpaceFlow Workspace', 'Cena podstawowa', amount(CATALOG['workspaceBase'])),
            ('Użytkownicy', f'{config.users} × {money(CATALOG["userRate"])}', config.users * amount(CATALOG['userRate']))]
    server = next(plan for plan in CATALOG['serverPlans'] if plan['id'] == config.server_plan)
    count = 2 if config.server_ha else 1
    rows.append((f'Serwer aplikacji {server["id"]}',
                 f'{count} × {server["vcpu"]} vCPU / {server["ram"]} GB RAM / {server["nvme"]} GB NVMe'
                 + (' · HA: dwa serwery' if config.server_ha else ' · jeden serwer'), count * amount(server['monthly'])))
    if config.database_plan != 'none':
        database = next(plan for plan in CATALOG['databasePlans'] if plan['id'] == config.database_plan)
        rows.append((f'{config.database_engine} {database["id"]}',
                     f'{database["vcpu"]} vCPU / {database["ram"]} GB RAM / {database["disk"]} GB dysku na instancję'
                     + (' · z repliką (HA)' if config.database_ha else ' · pojedyncza'),
                     amount(database['ha' if config.database_ha else 'single'])))
    else:
        rows.append(('Serwer bazy danych', 'Brak osobnego serwera bazy', amount(0)))
    rows.append(('Przestrzeń dyskowa', f'{config.storage} GB · {money(CATALOG["storageRate"])} / 100 GB',
                 amount(config.storage) / 100 * amount(CATALOG['storageRate'])))
    options = {option['id']: option for option in CATALOG['infrastructureOptions']}
    for key in ('waf', 'backup', 'vpn', 'logs'):
        if getattr(config, key):
            option = options[key]
            rows.append((option['name'], option['description'], amount(option['price'])))
    return rows


def render_offer(config):
    register_fonts()
    output = BytesIO()
    purple = colors.HexColor('#7138C9')
    ink = colors.HexColor('#30233F')
    muted = colors.HexColor('#80718E')
    pale = colors.HexColor('#F5EFFF')
    line = colors.HexColor('#E8DFF1')
    width = A4[0] - 88
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=44, rightMargin=44, topMargin=42, bottomMargin=48,
                            title='SpaceFlow - oferta konfiguracji', author='SpaceFlow', pageCompression=1)
    styles = {
        'brand': ParagraphStyle('brand', fontName='Document-Bold', fontSize=12, textColor=purple, leading=18),
        'title': ParagraphStyle('title', fontName='Document-Bold', fontSize=28, textColor=ink, leading=34),
        'body': ParagraphStyle('body', fontName='Document', fontSize=9, textColor=muted, leading=14),
        'name': ParagraphStyle('name', fontName='Document-Bold', fontSize=9, textColor=ink, leading=13),
        'detail': ParagraphStyle('detail', fontName='Document', fontSize=8, textColor=muted, leading=12),
        'price': ParagraphStyle('price', fontName='Document-Bold', fontSize=10, textColor=ink, leading=14, alignment=2),
        'tablehead': ParagraphStyle('tablehead', fontName='Document-Bold', fontSize=8, textColor=muted, leading=12),
        'total': ParagraphStyle('total', fontName='Document-Bold', fontSize=27, textColor=purple, leading=34, alignment=2),
    }
    p = lambda text, style='body': Paragraph(text, styles[style])
    date = datetime.now(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y')
    header = Table([[p('SPACE / FLOW', 'brand'), Paragraph(f'WYCENA DEMONSTRACYJNA<br/>{date}',
                    ParagraphStyle('date', parent=styles['detail'], alignment=2))]], colWidths=[width * .55, width * .45])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story = [header, Spacer(1, 28), p('Twoja przestrzeń.<br/>Twoje dobre flow.', 'title'), Spacer(1, 12),
             p('Oferta konfiguracji SpaceFlow Workspace'), Spacer(1, 24)]
    rows = quote_rows(config)
    total = sum(row[2] for row in rows)
    data = [[p('KONFIGURACJA', 'tablehead'), p('NETTO / MIESIĄC', 'tablehead')]]
    for name, description, price in rows:
        data.append([[p(name, 'name'), Spacer(1, 3), p(description, 'detail')], p(money(price), 'price')])
    table = Table(data, colWidths=[width - 124, 124], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), pale), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), .5, line),
    ]))
    story.append(table)
    total_box = Table([[p('MIESIĘCZNIE NETTO', 'tablehead'), p(money(total), 'total')]], colWidths=[width * .43, width * .57])
    total_box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), pale), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                 ('TOPPADDING', (0, 0), (-1, -1), 16), ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
                                 ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12)]))
    notes = [Spacer(1, 18), total_box, Spacer(1, 12),
             p('Ceny demonstracyjne. Do cen netto należy doliczyć VAT. Wdrożenie wyceniane osobno.', 'detail')]
    if config.server_ha and config.database_plan != 'none' and config.database_ha and config.waf and config.logs:
        notes += [Spacer(1, 8), p('Konfiguracja pod NIS2: HA serwera i bazy, WAF oraz analiza logów. '
                    'Same ustawienia techniczne nie potwierdzają pełnej zgodności z NIS2.', 'detail')]
    story.append(KeepTogether(notes))

    def footer(canvas, document):
        canvas.setStrokeColor(line)
        canvas.line(44, 35, A4[0] - 44, 35)
        canvas.setFillColor(muted)
        canvas.setFont('Document', 8)
        canvas.drawString(44, 22, 'SpaceFlow | Twoja prywatna przestrzeń pracy')
        canvas.drawRightString(A4[0] - 44, 22, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


@router.post('/api/pricing/offer', tags=['Wycena'])
def prepare_offer(config: OfferConfig):
    return Response(render_offer(config), media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="SpaceFlow-oferta.pdf"', 'Cache-Control': 'no-store'})
