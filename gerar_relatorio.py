from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

doc = Document()

# ── Margens ──────────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

# ── Helpers ──────────────────────────────────────────────────────────────────
def set_cell_bg(cell, hex_color):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)

def add_heading(doc, text, level=1, color_hex="1F4E79"):
    p    = doc.add_heading(text, level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in p.runs:
        run.font.color.rgb = RGBColor.from_string(color_hex)
    return p

def add_para(doc, text, bold=False, italic=False, size=10, color=None, space_before=0, space_after=4):
    p    = doc.add_paragraph()
    run  = p.add_run(text)
    run.bold   = bold
    run.italic = italic
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    return p

def add_bullet(doc, text, level=0, size=9.5):
    p   = doc.add_paragraph(style='List Bullet')
    run = p.add_run(text)
    run.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(2)
    return p

def add_table_row(table, cells_data, is_header=False, bg=None):
    row = table.add_row()
    for i, (text, bold) in enumerate(cells_data):
        cell = row.cells[i]
        cell.text = ''
        p    = cell.paragraphs[0]
        run  = p.add_run(text)
        run.bold = bold or is_header
        run.font.size = Pt(8.5) if not is_header else Pt(9)
        if is_header:
            run.font.color.rgb = RGBColor(255, 255, 255)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        if bg:
            set_cell_bg(cell, bg)
        elif is_header:
            set_cell_bg(cell, '1F4E79')
    return row

# ═══════════════════════════════════════════════════════════════════════════
# CAPA
# ═══════════════════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('\n\n\nMAPEAMENTO INDUSTRIAL')
run.bold = True
run.font.size = Pt(26)
run.font.color.rgb = RGBColor.from_string('1F4E79')

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
run2 = p2.add_run('POÇOS DE CALDAS – MG')
run2.bold = True
run2.font.size = Pt(18)
run2.font.color.rgb = RGBColor.from_string('2E75B6')

p3 = doc.add_paragraph()
p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
run3 = p3.add_run('Inteligência Comercial B2B | Prospecção Industrial | ESG & Sustentabilidade')
run3.italic = True
run3.font.size = Pt(12)
run3.font.color.rgb = RGBColor.from_string('595959')

p4 = doc.add_paragraph()
p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
run4 = p4.add_run(f'\nVersão 2025 — Gerado em {datetime.date.today().strftime("%d/%m/%Y")}')
run4.font.size = Pt(10)
run4.font.color.rgb = RGBColor.from_string('808080')

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 1. CONTEXTO MACRO
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '1. CONTEXTO MACRO DO POLO INDUSTRIAL', level=1)
add_para(doc,
    'Poços de Caldas é um dos polos industriais em maior expansão do Sul de Minas. '
    'O Distrito Industrial conta com 36 empresas em operação e 34 em fase de implantação, '
    'com aproximadamente R$ 2 bilhões em investimentos privados em 2024. '
    'Projeção de R$ 8 bilhões até 2030. O setor industrial lidera a geração de empregos '
    '— 834 vagas abertas apenas em 2024.',
    size=10)

doc.add_paragraph()

# ═══════════════════════════════════════════════════════════════════════════
# 2. TABELA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '2. EMPRESAS INDUSTRIAIS MAPEADAS (17 EMPRESAS)', level=1)

col_widths = [Cm(3.5), Cm(3.2), Cm(2.8), Cm(1.6), Cm(3.2), Cm(4.5)]
tbl = doc.add_table(rows=1, cols=6)
tbl.style = 'Table Grid'
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, w in enumerate(col_widths):
    for cell in tbl.columns[i].cells:
        cell.width = w

# cabeçalho
headers = ['Empresa', 'Segmento', 'CNAE', 'Porte', 'Endereço', 'Observações Estratégicas']
hdr_row = tbl.rows[0]
for i, h in enumerate(headers):
    cell = hdr_row.cells[i]
    cell.text = ''
    run = cell.paragraphs[0].add_run(h)
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(255, 255, 255)
    set_cell_bg(cell, '1F4E79')

# dados
rows_data = [
    ('Alcoa Alumínio S/A', 'Mineração / Metalurgia do Alumínio', '2451-2/00 | 0600-0/01', 'Grande',
     'Av. Alcoa, 5801 – Bortolan',
     '538 diretos + 680 indiretos; refinaria, química, refusão e pó de alumínio; 58+ anos no Brasil'),
    ('CBA – Cia. Brasileira de Alumínio', 'Mineração / Alumínio primário', '0710-1/00', 'Grande',
     'Estação Bauxita, S/N – Bortolan',
     'Fundada 1966; mineração sustentável; referência em ESG e reabilitação de áreas lavradas'),
    ('Prysmian Cabos e Sistemas', 'Cabos elétricos / Telecom', '2732-5/00', 'Grande',
     'Av. Alcoa, 5801 – Bortolan',
     '~500 diretos; lab. alta tensão (800 kV) – referência América do Sul; R$ 123 mi investidos'),
    ('Danone Ltda.', 'Alimentos / Nutrição infantil', '1052-0/00 | 1099-6/01', 'Grande',
     'Distrito Industrial',
     '2 plantas; R$ 250 mi em 3 anos; forte agenda ESG e programas sociais'),
    ('ThyssenKrupp', 'Metal-mecânica / Automotivo', '2949-2/99', 'Grande',
     'Distrito Industrial',
     'Primeira planta Indústria 4.0 da empresa no Brasil; R$ 120 mi até 2032'),
    ('Grupo Poçostec', 'Usinagem e Caldeiraria', '2550-1/01', 'Médio-Grande',
     'Av. Mansur Frayha, 4740',
     'R$ 35 mi em nova sede; fornecedor da Alcoa, Danone, Prysmian e ThyssenKrupp'),
    ('Valgroup', 'Plásticos / Embalagens / Reciclagem', '2222-6/00', 'Grande',
     'Distrito Industrial',
     '+7.000 colaboradores no grupo; produção, transformação e reciclagem de plásticos'),
    ('Viscotech', 'Plásticos técnicos / Polímeros', '2229-3/01', 'Pequeno-Médio',
     'Av. Celanese, 3100 – Bortolan',
     '+23 anos de mercado; fundada 2002; plásticos técnicos de alta especificação'),
    ('JR Plásticos', 'Reciclagem industrial / Plásticos', '3832-7/00', 'Pequeno-Médio',
     'Rod. Geraldo Martins – Bortolan Sul',
     'Reciclagem de plásticos; potencial alinhamento com agenda ESG e economia circular'),
    ('IKSO Equipamentos', 'Equipamentos industriais / Skids', '2829-1/00', 'Médio',
     'Poços de Caldas – MG',
     'Skids, EMEDs, seções de medição; projetos turnkey; engenharia e automação'),
    ('Viridis Mining', 'Mineração / Terras raras / Reciclagem de magnetos', '0899-1/99', 'Grande (implant.)',
     'Poços de Caldas – MG',
     'R$ 1,35 bi; JV com Ionic Rare Earths; pioneira em reciclagem de magnetos no Hemisfério Sul'),
    ('Althaia Farmacêutica', 'Farmacêutica / Suplementos', '2121-1/01', 'Médio-Grande (implant.)',
     'Distrito Industrial',
     'R$ 100 mi; 230 empregos; operação prevista 2026; genéricos + Equaliv'),
    ('Bolivar Plásticos', 'Plásticos / Embalagens', '2222-6/00', 'Pequeno-Médio',
     'Poços de Caldas – MG',
     'Uma das maiores em faturamento no segmento local; dados limitados online'),
    ('Tecnifox Ind. e Com.', 'Plásticos / Polímeros', '2229-3/01', 'Pequeno',
     'Poços de Caldas – MG',
     'Presente em rankings locais de plástico; baixa presença digital'),
    ('Gera Pet Embalagens', 'Reciclagem / Embalagens PET', '3832-7/00', 'Pequeno',
     'Poços de Caldas – MG',
     'Foco em PET reciclado; alinhamento com economia circular e ESG'),
    ('Caldas Química', 'Química industrial / Tratamento de água', '2012-6/00', 'Pequeno-Médio',
     'Poços de Caldas – MG',
     'Tratamento de água e efluentes; fornecedor potencial para todo o polo'),
    ('Ferrero do Brasil', 'Alimentos / Chocolates', '1093-7/01', 'Grande',
     'Poços de Caldas – MG',
     'Unidade de produção confirmada; marca global; potencial ESG e comunidade relevante'),
]

alt = False
for rd in rows_data:
    row = tbl.add_row()
    bg  = 'DEEAF1' if alt else 'FFFFFF'
    for i, text in enumerate(rd):
        cell = row.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(text)
        run.font.size = Pt(8)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_bg(cell, bg)
    alt = not alt

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 3. ENRIQUECIMENTO
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '3. ENRIQUECIMENTO — TIPO DE OPERAÇÃO E CADEIA DE VALOR', level=1)

enrich_data = [
    ('Alcoa', 'Mineração + Refinaria + Química + Transformação', 'Extrator primário / OEM'),
    ('CBA', 'Mineração + Beneficiamento', 'Extrator primário'),
    ('Prysmian', 'Fabricação + P&D', 'OEM – Produto final (cabos)'),
    ('Danone', 'Fabricação + Embalagem + Distribuição', 'Indústria de consumo final'),
    ('ThyssenKrupp', 'Fabricação de componentes', 'Tier 1 – Fornecedor automotivo'),
    ('Poçostec', 'Usinagem + Caldeiraria + Projetos', 'Fornecedor industrial (B2B puro)'),
    ('Valgroup', 'Transformação + Reciclagem + Embalagem', 'Transformador / Reciclador'),
    ('Viscotech', 'Transformação de plásticos técnicos', 'Fornecedor de insumos industriais'),
    ('JR Plásticos', 'Reciclagem + Reprocessamento', 'Reciclador / Fornecedor de resina reciclada'),
    ('IKSO', 'Montagem de equipamentos + Engenharia', 'Integrador / Fabricante de sistemas'),
    ('Viridis', 'Mineração + Reciclagem de magnetos', 'Extrator + Reciclador (transição energética)'),
    ('Althaia', 'Fabricação farmacêutica', 'Indústria de consumo final (B2B + B2C)'),
    ('Ferrero', 'Fabricação alimentícia', 'Indústria de consumo final'),
]

tbl2 = doc.add_table(rows=1, cols=3)
tbl2.style = 'Table Grid'
tbl2.alignment = WD_TABLE_ALIGNMENT.CENTER
for cell, txt in zip(tbl2.rows[0].cells, ['Empresa', 'Tipo de Operação', 'Posição na Cadeia']):
    cell.text = ''
    run = cell.paragraphs[0].add_run(txt)
    run.bold = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(255,255,255)
    set_cell_bg(cell, '2E75B6')

alt = False
for ed in enrich_data:
    row = tbl2.add_row()
    bg  = 'EBF3FB' if alt else 'FFFFFF'
    for i, txt in enumerate(ed):
        cell = row.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(txt)
        run.font.size = Pt(8.5)
        set_cell_bg(cell, bg)
    alt = not alt

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 4. CLUSTERIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '4. CLUSTERIZAÇÃO INDUSTRIAL', level=1)

clusters = [
    ('CLUSTER 1 — ALUMÍNIO E MINERAÇÃO METÁLICA', '1F4E79',
     'Alcoa · CBA · Poçostec (fornecedor)',
     ['Cadeia produtiva vertical: extração → refinamento → usinagem de peças',
      'Geração de demanda para fornecedores locais e serviços especializados',
      'Alta exposição a pauta ESG (reabilitação de minas, emissões, uso de água)']),
    ('CLUSTER 2 — METAL-MECÂNICA E SISTEMAS INDUSTRIAIS', '2E75B6',
     'ThyssenKrupp · Poçostec · IKSO',
     ['Cadeia automotiva e de equipamentos industriais',
      'Indústria 4.0, CNC, automação',
      'Forte demanda por tecnologia, fornecedores qualificados e RH técnico']),
    ('CLUSTER 3 — PLÁSTICOS, POLÍMEROS E RECICLAGEM', '375623',
     'Valgroup · Viscotech · JR Plásticos · Bolivar Plásticos · Tecnifox · Gera Pet',
     ['Polo de transformação plástica com reciclagem industrial',
      'Alta relevância para agenda de economia circular e ESG',
      'Interconexão: resinas → transformação → embalagem → reciclagem']),
    ('CLUSTER 4 — TRANSIÇÃO ENERGÉTICA E MINERAÇÃO ESTRATÉGICA', '7030A0',
     'Viridis Mining · Alcoa · CBA',
     ['Novo cluster emergente com alto potencial estratégico',
      'Terras raras para baterias, ímãs permanentes, energia eólica',
      'Conexão com reindustrialização e agenda de descarbonização nacional']),
    ('CLUSTER 5 — FARMACÊUTICA E SAÚDE', 'C00000',
     'Althaia (em implantação)',
     ['Cluster nascente; potencial de atrair fornecedores especializados',
      'Conexão com agenda ESG, saúde ocupacional, comunidade']),
    ('CLUSTER 6 — ALIMENTOS INDUSTRIALIZADOS', 'BF8F00',
     'Danone · Ferrero',
     ['Marcas globais com operação local relevante',
      'Alto impacto em ESG, emprego, comunidade e relacionamento institucional']),
    ('CLUSTER 7 — INFRAESTRUTURA ELÉTRICA', '00B0F0',
     'Prysmian',
     ['Único no segmento localmente, relevância na cadeia de energia e telecomunicações',
      'Lab de alta tensão – referência sul-americana']),
]

for name, color, empresas, bullets in clusters:
    p = doc.add_paragraph()
    run = p.add_run(name)
    run.bold = True; run.font.size = Pt(11)
    run.font.color.rgb = RGBColor.from_string(color)
    p.paragraph_format.space_before = Pt(6)
    add_para(doc, f'Empresas: {empresas}', bold=False, italic=True, size=9, color='595959')
    for b in bullets:
        add_bullet(doc, b)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 5. RANKING DE PROSPECÇÃO
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '5. RANKING DE PROSPECÇÃO B2B', level=1)

ranking = [
    ('🔴 ALTA',  'Alcoa',            'Grande porte, multinacional, alto orçamento ESG/comunidade, longa presença local'),
    ('🔴 ALTA',  'Prysmian',         '+R$ 123 mi investidos, expansão ativa, laboratório de referência sul-americana'),
    ('🔴 ALTA',  'Danone',           '2 fábricas, R$ 250 mi em 3 anos, forte agenda ESG e programas sociais robustos'),
    ('🔴 ALTA',  'ThyssenKrupp',     'Multinacional alemã, Indústria 4.0, R$ 120 mi até 2032, alta maturidade institucional'),
    ('🔴 ALTA',  'CBA',              'Grande grupo nacional, mineração sustentável, exposição pública a ESG e comunidade'),
    ('🔴 ALTA',  'Viridis Mining',   'R$ 1,35 bi de investimento, empresa emergente com alta necessidade de relacionamento local'),
    ('🟡 MÉDIA', 'Valgroup',         'Grande grupo nacional de plásticos, agenda ESG crescente, presença local confirmada'),
    ('🟡 MÉDIA', 'Grupo Poçostec',   'R$ 35 mi em nova sede, empresa em crescimento, alta maturidade para B2B'),
    ('🟡 MÉDIA', 'Althaia',          'Em implantação, R$ 100 mi, momento ideal para relacionamento inicial'),
    ('🟡 MÉDIA', 'IKSO',             'Médio porte, especializada, bom potencial de parceria técnica'),
    ('🟡 MÉDIA', 'Ferrero',          'Marca global, verificar estrutura ESG local'),
    ('🟢 BAIXA', 'Viscotech',        'Pequeno-Médio, nicho técnico, baixa presença digital'),
    ('🟢 BAIXA', 'JR Plásticos',     'Pequeno porte, potencial somente em pauta ambiental'),
    ('🟢 BAIXA', 'Bolivar Plásticos','Dados limitados, porte incerto'),
    ('🟢 BAIXA', 'Gera Pet',         'Pequeno porte, potencial somente em economia circular'),
    ('🟢 BAIXA', 'Tecnifox',         'Pequeno porte, baixa maturidade digital'),
    ('🟢 BAIXA', 'Caldas Química',   'Nicho específico, verificar porte real antes de abordar'),
]

tbl3 = doc.add_table(rows=1, cols=3)
tbl3.style = 'Table Grid'
for cell, txt in zip(tbl3.rows[0].cells, ['Prioridade', 'Empresa', 'Justificativa']):
    cell.text = ''
    run = cell.paragraphs[0].add_run(txt)
    run.bold = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(255,255,255)
    set_cell_bg(cell, '1F4E79')

colors_bg = {'🔴 ALTA': 'FFE7E7', '🟡 MÉDIA': 'FFF9E6', '🟢 BAIXA': 'E9F5E9'}
for prio, emp, just in ranking:
    row = tbl3.add_row()
    bg  = colors_bg.get(prio, 'FFFFFF')
    for i, txt in enumerate([prio, emp, just]):
        cell = row.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(txt)
        run.font.size = Pt(8.5)
        if i == 0: run.bold = True
        set_cell_bg(cell, bg)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 6. INTELIGÊNCIA COMERCIAL
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '6. INTELIGÊNCIA COMERCIAL — OPORTUNIDADES POR EMPRESA', level=1)

oportunidades = [
    ('ALCOA', '🔴 ALTA PRIORIDADE', '1F4E79',
     'Gestão de stakeholders locais, reabilitação de áreas mineradas, pressão regulatória ambiental, relacionamento com comunidades do entorno (Bortolan)',
     'Programas de relacionamento comunitário, ESG reporting, tecnologia ambiental, projetos sociais locais',
     'Via Gerência de Sustentabilidade ou Relações Institucionais; referência em biodiversidade e pós-mineração'),
    ('PRYSMIAN', '🔴 ALTA PRIORIDADE', '1F4E79',
     'Integração de fornecedores locais, comunicação com comunidade, gestão de talentos para o laboratório de alta tensão',
     'Parceria em inovação, fornecimento especializado, programa de empregabilidade técnica',
     'Via Gerência Industrial ou RH; destacar o laboratório de referência como âncora de relacionamento'),
    ('DANONE', '🔴 ALTA PRIORIDADE', '1F4E79',
     'Cadeia de fornecimento local, engajamento comunitário, nutrição e saúde pública, logística',
     'Responsabilidade social, programas de nutrição infantil, relacionamento com prefeitura e associações',
     'Via Gerência de Sustentabilidade ou Assuntos Corporativos; estrutura de ESG mais madura do setor alimentício'),
    ('THYSSENKRUPP', '🔴 ALTA PRIORIDADE', '1F4E79',
     'Gestão de fornecedores Tier 2 locais, desenvolvimento de RH técnico, digitalização da cadeia',
     'Qualificação de fornecedores locais, relacionamento institucional, Indústria 4.0',
     'Via Gerência de Operações ou Supply Chain; empresa alemã valoriza formalidade e dados'),
    ('CBA', '🔴 ALTA PRIORIDADE', '1F4E79',
     'Reabilitação de minas, gestão de resíduos, pressão ESG, relacionamento com comunidades rurais do entorno',
     'Programas ambientais, monitoramento de impacto, relacionamento comunitário, comunicação institucional',
     'Via Gerência de Meio Ambiente ou Relações Institucionais'),
    ('VIRIDIS MINING', '🔴 ALTA PRIORIDADE — JANELA URGENTE', 'C00000',
     'Empresa estrangeira (australiana) nova no território; necessidade urgente de mapeamento de stakeholders, licenciamento social, gestão de expectativas comunitárias',
     'Alta urgência e alta abertura — é o momento ideal. Relacionamento com lideranças locais, suporte em comunicação e engajamento social',
     'Diretamente via C-Level ou Gerência de Projetos; empresa em fase de estruturação — qualquer suporte é valioso'),
]

for nome, prio, cor, dores, oport, abord in oportunidades:
    p = doc.add_paragraph()
    run = p.add_run(f'{nome}  |  {prio}')
    run.bold = True; run.font.size = Pt(11)
    run.font.color.rgb = RGBColor.from_string(cor)
    p.paragraph_format.space_before = Pt(8)

    add_para(doc, 'Possíveis dores:', bold=True, size=9)
    add_bullet(doc, dores)
    add_para(doc, 'Oportunidade:', bold=True, size=9)
    add_bullet(doc, oport)
    add_para(doc, 'Abordagem sugerida:', bold=True, size=9)
    add_bullet(doc, abord)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 7. MAPA DE STAKEHOLDERS
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '7. MAPA DE STAKEHOLDERS — DECISORES POTENCIAIS', level=1)

stakeholders = [
    ('Alcoa',           'Gerente de Sustentabilidade / Gerente de Relações Comunitárias', 'ESG, Meio Ambiente'),
    ('CBA',             'Gerente de Responsabilidade Social / Ambiental',                 'ESG, Comunidade'),
    ('Prysmian',        'Gerente Industrial / HRBP',                                      'RH, Operações'),
    ('Danone',          'Gerente de Assuntos Corporativos / Sustentabilidade',            'ESG, Comunicação'),
    ('ThyssenKrupp',    'Plant Manager / Gerente de Supply Chain',                        'Operações, Compras'),
    ('Viridis Mining',  'CEO Brasil / Gerente de Projetos / Relações Institucionais',     'C-Level, Projetos'),
    ('Poçostec',        'Diretor Comercial / Diretor Industrial',                         'Comercial, Operações'),
    ('Althaia',         'Diretor de Operações / RH',                                      'Implantação, Gestão'),
    ('Valgroup',        'Gerente de Sustentabilidade / Compras',                          'ESG, Supply Chain'),
    ('Ferrero',         'Gerente de Assuntos Corporativos / RSC',                         'ESG, Comunidade'),
]

tbl4 = doc.add_table(rows=1, cols=3)
tbl4.style = 'Table Grid'
for cell, txt in zip(tbl4.rows[0].cells, ['Empresa', 'Função-Alvo', 'Área']):
    cell.text = ''
    run = cell.paragraphs[0].add_run(txt)
    run.bold = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(255,255,255)
    set_cell_bg(cell, '2E75B6')

alt = False
for sd in stakeholders:
    row = tbl4.add_row()
    bg  = 'EBF3FB' if alt else 'FFFFFF'
    for i, txt in enumerate(sd):
        cell = row.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(txt)
        run.font.size = Pt(8.5)
        if i == 0: run.bold = True
        set_cell_bg(cell, bg)
    alt = not alt

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 8. INSIGHTS ACIONÁVEIS
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '8. INSIGHTS ACIONÁVEIS', level=1)

insights = [
    'Viridis é a janela de oportunidade mais urgente — empresa estrangeira, investimento bilionário, em fase inicial, com enorme necessidade de suporte local para licenciamento social e stakeholders.',
    'O trinômio Alcoa–Prysmian–Poçostec forma a espinha dorsal do polo metal-elétrico local. Entrar como parceiro em qualquer um abre acesso aos outros.',
    'Danone e Ferrero são as âncoras do segmento alimentício — forte agenda ESG e programas comunitários maduros; abordagem via assuntos corporativos.',
    'Cluster de plásticos e reciclagem (Valgroup, JR Plásticos, Gera Pet) tem alta aderência à pauta de economia circular — tema em ascensão regulatória (PNRS, TRRS).',
    'Althaia entra em 2026 — o relacionamento deve começar AGORA, na fase de obras e estruturação, quando a empresa está mais receptiva.',
    'O Distrito Industrial está em plena expansão (R$ 2 bi / 34 empresas em implantação) — há um pipeline de prospecção que se renova continuamente com novas empresas anunciadas.',
    'ThyssenKrupp valoriza dados e formalidade — abordagem deve ser técnica, baseada em benchmarks e resultados mensuráveis.',
    'Prysmian tem o laboratório de alta tensão mais importante da América do Sul em Poços de Caldas — usar isso como âncora de orgulho regional em qualquer abordagem.',
]

for i, insight in enumerate(insights, 1):
    p = doc.add_paragraph()
    run1 = p.add_run(f'{i}. ')
    run1.bold = True; run1.font.size = Pt(10)
    run1.font.color.rgb = RGBColor.from_string('1F4E79')
    run2 = p.add_run(insight)
    run2.font.size = Pt(10)
    p.paragraph_format.space_after = Pt(6)

doc.add_page_break()

# ═══════════════════════════════════════════════════════════════════════════
# 9. ESTRATÉGIA DE PROSPECÇÃO DE VAGAS — RSC / COMUNIDADES / SUSTENTABILIDADE
# ═══════════════════════════════════════════════════════════════════════════
add_heading(doc, '9. ESTRATÉGIA DE PROSPECÇÃO DE VAGAS', level=1)
add_para(doc, 'Área: Relacionamento com Comunidades | Responsabilidade Social | Sustentabilidade', bold=True, size=12, color='2E75B6')
add_para(doc, 'Polo Industrial de Poços de Caldas — MG | Versão 2025', italic=True, size=10, color='595959')

doc.add_paragraph()

add_heading(doc, '9.1 Contexto e Posicionamento', level=2)
add_para(doc,
    'Poços de Caldas vive uma janela histórica de expansão industrial. Empresas multinacionais '
    'com forte agenda ESG (Alcoa, Danone, Prysmian, ThyssenKrupp) convivem com entrantes que '
    'precisam construir sua presença local do zero (Viridis Mining, Althaia). '
    'Esse contexto cria demanda real e crescente por profissionais de RSC, Sustentabilidade e '
    'Relacionamento com Comunidades — tanto em posições formais quanto em consultoria e projetos.',
    size=10)

add_heading(doc, '9.2 Empresas Prioritárias para Prospecção de Vagas', level=2)

vagas_data = [
    ('Alcoa', '🔴 Alta', 'Gerente/Analista de Comunidades, Relações Institucionais, ESG', 'linkedin.com/company/alcoa'),
    ('CBA', '🔴 Alta', 'Analista de RSC, Gestor Ambiental, Relações com Comunidade', 'linkedin.com/company/cba-aluminio'),
    ('Danone', '🔴 Alta', 'Gerente de Sustentabilidade, Analista de Assuntos Corporativos', 'linkedin.com/company/danone'),
    ('Prysmian', '🔴 Alta', 'Analista de RSC / ESG, Comunicação Institucional, RH', 'linkedin.com/company/prysmian-group'),
    ('ThyssenKrupp', '🔴 Alta', 'Analista ESG, Relações Institucionais, Sustentabilidade', 'linkedin.com/company/thyssenkrupp'),
    ('Viridis Mining', '🔴 Alta (urgente)', 'Gestor de Stakeholders, Relações com Comunidade, Licença Social', 'linkedin.com/company/viridis-mining'),
    ('Valgroup', '🟡 Média', 'Analista de Sustentabilidade / Economia Circular', 'linkedin.com/company/valgroup'),
    ('Althaia', '🟡 Média', 'Analista de RSC, Comunicação Institucional (implantação)', 'linkedin.com/company/althaia'),
    ('Ferrero', '🟡 Média', 'Gerente de RSC / Assuntos Corporativos', 'linkedin.com/company/ferrero'),
]

tbl5 = doc.add_table(rows=1, cols=4)
tbl5.style = 'Table Grid'
for cell, txt in zip(tbl5.rows[0].cells, ['Empresa', 'Prioridade', 'Cargos-Alvo', 'LinkedIn']):
    cell.text = ''
    run = cell.paragraphs[0].add_run(txt)
    run.bold = True; run.font.size = Pt(9); run.font.color.rgb = RGBColor(255,255,255)
    set_cell_bg(cell, '1F4E79')

alt = False
for vd in vagas_data:
    row = tbl5.add_row()
    bg  = colors_bg.get(vd[1].split(' ')[0] + ' ' + vd[1].split(' ')[1] if len(vd[1].split()) > 1 else vd[1], 'FFFFFF')
    if '🔴' in vd[1]: bg = 'FFE7E7'
    elif '🟡' in vd[1]: bg = 'FFF9E6'
    else: bg = 'E9F5E9'
    for i, txt in enumerate(vd):
        cell = row.cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(txt)
        run.font.size = Pt(8.5)
        if i == 0: run.bold = True
        set_cell_bg(cell, bg)
    alt = not alt

doc.add_page_break()

add_heading(doc, '9.3 Estratégia de Abordagem ao RH', level=2)

etapas = [
    ('ETAPA 1 — PREPARAÇÃO DO PERFIL (Semana 1–2)', '1F4E79', [
        'Atualizar LinkedIn com palavras-chave: RSC, ESG, Sustentabilidade, Relacionamento com Comunidades, Licença Social, Stakeholders',
        'Incluir no "Sobre": experiência com comunidades, projetos sociais, indicadores ESG, diálogo multipartes',
        'Criar portfólio digital (PDF ou Notion): projetos realizados, resultados mensuráveis, metodologias usadas',
        'Adaptar currículo para cada segmento: mineração, alimentos, farmacêutica, industrial',
    ]),
    ('ETAPA 2 — MAPEAMENTO E CONEXÃO (Semana 2–4)', '2E75B6', [
        'Seguir as páginas das 9 empresas prioritárias no LinkedIn',
        'Conectar com profissionais de RH, Sustentabilidade e RSC dessas empresas no LinkedIn (com mensagem personalizada)',
        'Acompanhar vagas nas páginas de Carreiras dos sites corporativos (especialmente Alcoa, Danone, Prysmian)',
        'Cadastrar currículo nos sites de Carreiras de cada empresa — mesmo sem vaga aberta',
        'Configurar alertas no LinkedIn Jobs: "Sustentabilidade Poços de Caldas", "RSC Minas Gerais", "Relações Comunitárias Sul de Minas"',
    ]),
    ('ETAPA 3 — ABORDAGEM DIRETA AO RH (Semana 3–6)', 'C00000', [
        'Enviar mensagem personalizada no LinkedIn para HRBP ou Gerente de RH de cada empresa-alvo',
        'Modelo de mensagem: apresentação em 3 linhas + proposta de valor clara + pedido de conexão (não de vaga)',
        'Priorizar Viridis Mining e Althaia: empresas em estruturação que ainda não têm time local formado',
        'Para empresas com vaga aberta: candidatura formal + mensagem ao recrutador reforçando interesse',
        'Para empresas sem vaga: abordagem de "candidatura espontânea estruturada" — demonstre que você conhece o contexto delas',
    ]),
    ('ETAPA 4 — RELACIONAMENTO INSTITUCIONAL (Mês 2–3)', '375623', [
        'Participar de eventos do Distrito Industrial de Poços de Caldas (sessões da Câmara Municipal, eventos da Prefeitura)',
        'Conectar com ACIP (Associação Comercial e Industrial de Poços de Caldas)',
        'Acompanhar notícias do polo industrial local (Diário do Comércio, Poços Já, Onda Poços)',
        'Participar de grupos do LinkedIn sobre ESG, RSC e mineração no Brasil',
        'Construir presença como referência no tema — artigos, comentários, compartilhamentos sobre o polo local',
    ]),
    ('ETAPA 5 — DIFERENCIAÇÃO NA ENTREVISTA', 'BF8F00', [
        'Demonstrar conhecimento do contexto local: citar Viridis, expansão do Distrito Industrial, clusters industriais',
        'Apresentar cases concretos com indicadores (ex: N famílias impactadas, % de satisfação, indicadores GRI)',
        'Mostrar familiaridade com frameworks: GRI, ODS/SDGs, ISO 26000, AA1000 SES (Stakeholder Engagement Standard)',
        'Conectar sua proposta de valor com as dores específicas da empresa (ver Seção 6 deste documento)',
        'Ter uma "proposta de 90 dias": o que você faria nos primeiros 3 meses no cargo',
    ]),
]

for titulo, cor, bullets in etapas:
    p = doc.add_paragraph()
    run = p.add_run(titulo)
    run.bold = True; run.font.size = Pt(11)
    run.font.color.rgb = RGBColor.from_string(cor)
    p.paragraph_format.space_before = Pt(8)
    for b in bullets:
        add_bullet(doc, b)

doc.add_page_break()

add_heading(doc, '9.4 Modelos de Mensagem para LinkedIn (RH)', level=2)

mensagens = [
    ('Para empresa com VAGA ABERTA (ex: Alcoa)', '1F4E79',
     'Olá [Nome], vi a vaga de [cargo] na Alcoa em Poços de Caldas e gostaria de reforçar meu interesse. '
     'Tenho experiência em [X anos] com relacionamento com comunidades e RSC no setor industrial, '
     'incluindo [mencione 1 projeto/resultado relevante]. '
     'Acredito que meu perfil pode contribuir com a agenda de sustentabilidade da Alcoa na região. '
     'Posso compartilhar meu portfólio se tiver interesse. Obrigado(a)!'),
    ('Para empresa SEM VAGA — Candidatura Espontânea (ex: Viridis Mining)', 'C00000',
     'Olá [Nome], acompanho com grande interesse o projeto da Viridis Mining em Poços de Caldas — '
     'um investimento pioneiro que vai demandar uma estrutura sólida de relacionamento com stakeholders locais. '
     'Tenho formação e experiência em [área] com foco em [licença social / engajamento comunitário / ESG]. '
     'Estaria à disposição para uma conversa sobre como posso contribuir nesse momento de estruturação. '
     'Podemos conversar?'),
    ('Para empresa EM IMPLANTAÇÃO (ex: Althaia)', '375623',
     'Olá [Nome], estou acompanhando o projeto da Althaia em Poços de Caldas com muito entusiasmo. '
     'Sei que empresas nessa fase precisam construir relacionamentos locais sólidos desde o início — '
     'com comunidade, poder público e fornecedores. '
     'Tenho experiência exatamente nessa etapa de estruturação de áreas de RSC e relações institucionais. '
     'Seria ótimo trocar uma ideia sobre o projeto. Fico à disposição!'),
]

for titulo, cor, texto in mensagens:
    p = doc.add_paragraph()
    run = p.add_run(titulo)
    run.bold = True; run.font.size = Pt(10)
    run.font.color.rgb = RGBColor.from_string(cor)

    p2 = doc.add_paragraph()
    p2.style = doc.styles['Normal']
    run2 = p2.add_run(f'"{texto}"')
    run2.italic = True; run2.font.size = Pt(9)
    run2.font.color.rgb = RGBColor.from_string('404040')
    p2.paragraph_format.left_indent  = Cm(1)
    p2.paragraph_format.right_indent = Cm(1)
    p2.paragraph_format.space_after  = Pt(8)

add_heading(doc, '9.5 Competências-Chave para Destacar', level=2)

competencias = [
    ('Técnicas (Hard Skills)',
     ['Elaboração e gestão de programas de investimento social',
      'Mapeamento e engajamento de stakeholders (AA1000 SES)',
      'Relatórios ESG (GRI, CDP, SASB)',
      'Processos de licenciamento socioambiental',
      'Indicadores sociais e avaliação de impacto',
      'Diálogo com lideranças comunitárias e poder público',
      'Conhecimento de legislação ambiental e social (PNRS, EIA/RIMA, consulta prévia)']),
    ('Comportamentais (Soft Skills)',
     ['Escuta ativa e empatia com comunidades',
      'Comunicação assertiva em múltiplos registros (técnico, comunitário, institucional)',
      'Gestão de conflitos e mediação',
      'Visão sistêmica e pensamento estratégico',
      'Capacidade de construir relacionamentos de longo prazo',
      'Autonomia e proatividade (especialmente em empresas em estruturação)']),
]

for titulo, items in competencias:
    add_para(doc, titulo, bold=True, size=10, color='1F4E79')
    for item in items:
        add_bullet(doc, item)
    doc.add_paragraph()

# rodapé / última linha
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run(f'Documento gerado em {datetime.date.today().strftime("%d/%m/%Y")} | Inteligência Comercial B2B — Polo Industrial de Poços de Caldas (MG)')
run.font.size = Pt(8)
run.font.color.rgb = RGBColor.from_string('A0A0A0')
run.italic = True

# ── Salvar ────────────────────────────────────────────────────────────────
output_path = '/home/user/fala-comunidade/Mapeamento_Industrial_Pocos_de_Caldas_2025.docx'
doc.save(output_path)
print(f'Arquivo salvo: {output_path}')
