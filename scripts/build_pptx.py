"""
Build the presentation deck: reports/Olist_Presentation.pptx (16:9, 11 slides).

Run:  python -m scripts.build_pptx
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from src.config import FIGURES_DIR, REPORTS_DIR

INK = RGBColor(0x1B, 0x27, 0x33)
MUTED = RGBColor(0x6B, 0x7A, 0x8A)
PRIMARY = RGBColor(0x0B, 0x6E, 0x99)
DEEP = RGBColor(0x0B, 0x3C, 0x56)
TEAL = RGBColor(0x1F, 0x9E, 0x89)
ACCENT = RGBColor(0xF2, 0xA9, 0x3B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xF5, 0xF7, 0xFA)

W, H = Inches(13.333), Inches(7.5)


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    return prs


def blank(prs: Presentation):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    return s


def textbox(slide, x, y, w, h, text, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
            spacing=1.0, font="Calibri"):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = font
    p.line_spacing = spacing
    return tb


def bullets(slide, x, y, w, h, items, size=13, color=INK, space=6):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space)
        bold_prefix = None
        if isinstance(item, tuple):
            bold_prefix, item = item
        if bold_prefix:
            r0 = p.add_run()
            r0.text = bold_prefix + " "
            r0.font.bold = True
            r0.font.size = Pt(size)
            r0.font.color.rgb = PRIMARY
            r0.font.name = "Calibri"
        r = p.add_run()
        r.text = item
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.name = "Calibri"
    return tb


def header(slide, title, kicker=None):
    bar = slide.shapes.add_shape(1, 0, 0, W, Inches(1.05))
    bar.fill.solid()
    bar.fill.fore_color.rgb = DEEP
    bar.line.fill.background()
    bar.shadow.inherit = False
    textbox(slide, Inches(0.55), Inches(0.22), Inches(11), Inches(0.6), title,
            size=24, bold=True, color=WHITE)
    if kicker:
        textbox(slide, Inches(0.55), Inches(0.68), Inches(12), Inches(0.3), kicker,
                size=11, color=RGBColor(0xBF, 0xD8, 0xE4))


def card(slide, x, y, w, h, label, value, sub=""):
    box = slide.shapes.add_shape(5, x, y, w, h)
    box.fill.solid()
    box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = RGBColor(0xE3, 0xE8, 0xEE)
    box.line.width = Pt(0.75)
    box.shadow.inherit = False
    textbox(slide, x + Inches(0.16), y + Inches(0.12), w - Inches(0.3), Inches(0.3),
            label.upper(), size=9.5, bold=True, color=MUTED)
    textbox(slide, x + Inches(0.16), y + Inches(0.38), w - Inches(0.3), Inches(0.5),
            value, size=22, bold=True, color=INK)
    if sub:
        textbox(slide, x + Inches(0.16), y + Inches(0.86), w - Inches(0.3), Inches(0.3),
                sub, size=9.5, color=MUTED)


def insight_strip(slide, text, y=None):
    """Bottom callout bar: the one sentence the audience should leave with."""
    y = y if y is not None else H - Inches(1.35)
    box = slide.shapes.add_shape(5, Inches(0.55), y, Inches(12.25), Inches(0.95))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xFF, 0xF8, 0xEC)
    box.line.color.rgb = RGBColor(0xF5, 0xDD, 0xB4)
    box.line.width = Pt(0.75)
    box.shadow.inherit = False
    bar = slide.shapes.add_shape(1, Inches(0.55), y, Inches(0.08), Inches(0.95))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False
    textbox(slide, Inches(0.85), y + Inches(0.17), Inches(11.7), Inches(0.7),
            text, size=13, bold=True, color=RGBColor(0x6B, 0x4A, 0x00))


def picture(slide, name, x, y, w=None, h=None):
    path = FIGURES_DIR / name
    if not path.exists():
        return
    if w is not None:
        slide.shapes.add_picture(str(path), x, y, width=w)
    else:
        slide.shapes.add_picture(str(path), x, y, height=h)


def footer(slide, text):
    textbox(slide, Inches(0.55), H - Inches(0.42), Inches(12.2), Inches(0.3),
            text, size=9, color=MUTED)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def build() -> Path:
    prs = new_deck()

    # ---------------------------------------------------------------- 1 title
    s = blank(prs)
    band = s.shapes.add_shape(1, 0, 0, W, Inches(4.5))
    band.fill.solid()
    band.fill.fore_color.rgb = DEEP
    band.line.fill.background()
    band.shadow.inherit = False
    accent = s.shapes.add_shape(1, 0, Inches(4.5), W, Inches(0.09))
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT
    accent.line.fill.background()
    accent.shadow.inherit = False

    textbox(s, Inches(0.9), Inches(1.25), Inches(11.5), Inches(0.4),
            "DATA ANALYTICS PROJECT", size=13, bold=True, color=RGBColor(0x8F, 0xC5, 0xD8))
    textbox(s, Inches(0.9), Inches(1.75), Inches(11.5), Inches(1.3),
            "E-commerce Sales &\nCustomer Behaviour Analysis", size=40, bold=True, color=WHITE,
            spacing=0.95)
    textbox(s, Inches(0.9), Inches(3.35), Inches(11.5), Inches(0.5),
            "Olist Brazilian E-commerce · 96,478 delivered orders · R$ 15.42M revenue", size=15,
            color=RGBColor(0xCF, 0xE3, 0xEC))
    textbox(s, Inches(0.9), Inches(5.0), Inches(5.4), Inches(1.4),
            "Question: how do we grow revenue,\nand which customers are actually valuable?",
            size=16, bold=True, color=INK, spacing=1.2)
    textbox(s, Inches(7.0), Inches(5.0), Inches(5.4), Inches(1.4),
            "Python (Pandas, Matplotlib, Seaborn) · SQL · Power BI / Plotly · GitHub",
            size=11, color=MUTED)
    notes(s, "Project brief: analyse Olist sales, customers and products to recommend how to grow "
             "revenue and identify the most valuable customers.")

    # ------------------------------------------------------- 2 problem/method
    s = blank(prs)
    header(s, "Problem, data and approach",
           "9 relational tables → cleaned warehouse → SQL + Python analysis → dashboard → recommendations")
    bullets(s, Inches(0.55), Inches(1.35), Inches(6.0), Inches(4.6), [
        ("Goal —", "tell the business where revenue comes from, who the valuable customers are, and what to change."),
        ("Data —", "Olist Brazilian E-commerce (Kaggle): orders, items, payments, reviews, customers, products, sellers, geolocation."),
        ("Scale —", "99,441 orders → 96,478 delivered, 110,197 items, 93,358 customers, 95,832 reviews."),
        ("Tools —", "Pandas for cleaning, SQL for business queries, Matplotlib/Seaborn for EDA, Plotly + Power BI for the dashboard."),
        ("Deliverables —", "notebook, SQL file, dashboard, report and this deck."),
    ], size=12.5, space=10)

    picture(s, "01_monthly_revenue_trend.png", Inches(6.95), Inches(1.45), w=Inches(6.0))
    insight_strip(s, "Every insight in this deck depends on one thing: the joins are safe — item revenue and "
                     "payment revenue agree within 0.02%.", y=Inches(5.25))

    # ------------------------------------------------------ 3 data cleaning
    s = blank(prs)
    header(s, "Data preparation: what had to be fixed",
           "13 clean-up decisions, all reproducible in src/etl.py")
    bullets(s, Inches(0.55), Inches(1.35), Inches(6.2), Inches(4.8), [
        ("5 order + 3 review dates", "were text → converted to real timestamps (otherwise no delivery metrics)."),
        ("customer_id", "is regenerated per order → frequency must use customer_unique_id."),
        ("order_items", "is item-grain → order KPIs need a one-row-per-order fact, or revenue multiplies."),
        ("Payments", "103,886 rows for 99,441 orders → collapsed to 1 row/order."),
        ("Reviews", "551 orders had 2+ reviews → kept the latest answer."),
        ("Geolocation", "1,000,163 rows → 19,015 zip-prefix centroids (no join explosion)."),
        ("Cancelled / unavailable", "1,234 orders (1.2%) excluded from the revenue universe."),
        ("Reconciliation", "item revenue vs payment revenue agree within 0.02% → joins are safe."),
    ], size=12, space=8)

    box = s.shapes.add_shape(5, Inches(7.05), Inches(1.5), Inches(5.75), Inches(4.2))
    box.fill.solid()
    box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = RGBColor(0xE3, 0xE8, 0xEE)
    box.shadow.inherit = False
    textbox(s, Inches(7.3), Inches(1.7), Inches(5.2), Inches(0.4), "RESULTING ANALYTICAL BASE",
            size=10, bold=True, color=MUTED)
    for i, (label, value) in enumerate([
        ("Delivered orders", "96,478"),
        ("Items", "110,197"),
        ("Customers", "93,358"),
        ("Revenue", "R$ 15.42M"),
        ("Average order value", "R$ 159.86"),
        ("Date range", "Sep 2016 – Aug 2018"),
    ]):
        y = Inches(2.15 + i * 0.58)
        textbox(s, Inches(7.3), y, Inches(3.0), Inches(0.35), label, size=11.5, color=MUTED)
        textbox(s, Inches(10.2), y, Inches(2.4), Inches(0.35), value, size=12.5, bold=True,
                color=INK, align=PP_ALIGN.RIGHT)

    # --------------------------------------------------------------- 4 KPIs
    s = blank(prs)
    header(s, "The business at a glance", "All figures: delivered orders, Sep 2016 – Aug 2018")
    kpis = [
        ("Revenue", "R$ 15.42M", "net of vouchers"),
        ("Orders", "96,478", "1.14 items per order"),
        ("Avg order value", "R$ 159.86", "flat for 20 months"),
        ("Customers", "93,358", "3.0% buy twice"),
        ("Avg review", "4.16 / 5", "12.8% are 1–2 star"),
        ("Delivery", "12.6 days", "promised 23.7 days"),
        ("Late orders", "8.1%", "7,826 orders"),
        ("Repeat revenue", "5.6%", "97% buy once"),
    ]
    for i, (label, value, sub) in enumerate(kpis):
        row, col = divmod(i, 4)
        card(s, Inches(0.55 + col * 3.13), Inches(1.4 + row * 1.42), Inches(2.9), Inches(1.26),
             label, value, sub)
    textbox(s, Inches(0.55), Inches(4.32), Inches(12.2), Inches(0.4),
            "Growth is volume-driven: 750 orders/month (Jan-2017) → 7,289 (Nov-2017), while the basket "
            "never moved. That single fact sets the whole recommendation.",
            size=12, color=INK)
    picture(s, "01_monthly_revenue_trend.png", Inches(0.55), Inches(4.85), w=Inches(12.2))

    # ------------------------------------------------------------ 5 growth
    s = blank(prs)
    header(s, "Revenue: a growth story that stalled",
           "Jan-2017 → Nov-2017: +806% · Nov-2017 Black Friday: +53.6% MoM · Dec-2017: −26.9%")
    picture(s, "01_monthly_revenue_trend.png", Inches(0.5), Inches(1.35), w=Inches(7.6))
    bullets(s, Inches(8.35), Inches(1.55), Inches(4.5), Inches(4.2), [
        ("Orders, not baskets —", "AOV held at R$146–170 for 20 months."),
        ("A single spike —", "Nov-2017 reached R$1.15M, then revenue settled at R$1.0–1.1M."),
        ("Seasonality —", "November runs ~R$38k/day vs ~R$23k in September."),
        ("Implication —", "+10% AOV is worth ~R$1.5M/year with no extra acquisition spend."),
    ], size=12, space=10)
    insight_strip(s, "The next R$1M has to come from basket size or retention — volume growth has flattened.",
                  y=Inches(5.35))

    # ---------------------------------------------------------- 6 products
    s = blank(prs)
    header(s, "Products: broad catalogue, shallow concentration",
           "71 categories · top 10 = 62.4% of revenue · 28.1% of SKUs make 80% of revenue")
    picture(s, "06_category_aov.png", Inches(0.4), Inches(1.3), w=Inches(6.5))
    picture(s, "11_product_pareto.png", Inches(7.0), Inches(1.3), w=Inches(5.9))
    bullets(s, Inches(0.55), Inches(5.15), Inches(12.2), Inches(0.8), [
        ("AOV spread 2.9x —", "Office Furniture R$267/order vs Telephony R$93: equal traffic, unequal revenue."),
        ("Long tail —", "the bottom half of the catalogue returns only 9.0% of revenue but carries full cost."),
    ], size=11, space=3)
    insight_strip(s, "Merchandise the top: the first 9,053 SKUs already carry 80% of revenue.")

    # --------------------------------------------------------- 7 customers
    s = blank(prs)
    header(s, "Customers: no loyalty to manage, high individual value",
           "RFM on customer_unique_id · R and M in quintiles · F in 1 / 2 / 3+ buckets (97% buy once)")
    picture(s, "08_rfm_segments.png", Inches(0.35), Inches(1.35), w=Inches(8.0))
    bullets(s, Inches(8.55), Inches(1.45), Inches(4.4), Inches(4.2), [
        ("97% buy once —", "repeat buyers are only 5.6% of revenue."),
        ("Champions —", "1,129 customers (1.2%) = 2.5% of revenue, R$339 each (2.1x average)."),
        ("Cannot Lose Them —", "757 high-spend customers already 12m+ absent, R$358 each."),
        ("Concentration —", "top 1% of customers = 10.3% of revenue, top 5% = 26.8%."),
        ("Read —", "manage value at the individual level, not by segment."),
    ], size=11, space=8)
    insight_strip(s, "The highest-value customers are 1,886 people worth R$339–358 each — "
                     "a list, not a segment.", y=Inches(5.05))

    # ---------------------------------------------------------- 8 cohort
    s = blank(prs)
    header(s, "Retention: the structural weakness",
           "Monthly cohort retention never exceeds 0.7% after the first purchase")
    picture(s, "10_cohort_retention.png", Inches(0.4), Inches(1.3), w=Inches(7.9))
    bullets(s, Inches(8.55), Inches(1.55), Inches(4.4), Inches(4.0), [
        ("Flat and decaying —", "customers do not come back; there is no revival in later months."),
        ("Right-censoring —", "cohorts after 2018-02 have fewer observable months; read by column."),
        ("Consequence —", "a loyalty programme is the wrong investment; first-90-day activation is the right one."),
    ], size=11.5, space=10)
    insight_strip(s, "No loyalty programme fixes a base that buys once — activation in the first 90 days does.")

    # -------------------------------------------------------- 9 delivery
    s = blank(prs)
    header(s, "Delivery is the reputation lever",
           "Late orders average 2.57 stars vs 4.29 on time · 54.1% of late orders become 1–2 star reviews")
    picture(s, "04_review_vs_delay.png", Inches(0.3), Inches(1.3), w=Inches(6.9))
    picture(s, "07_geography.png", Inches(7.25), Inches(1.35), w=Inches(5.7))
    bullets(s, Inches(0.55), Inches(5.05), Inches(12.2), Inches(0.9), [
        ("Where it breaks —", "North-East 14.3% late vs 7.5% elsewhere; AL 23.9%, MA 19.7%, PI 16.0%, CE 15.3%."),
        ("Over-promising —", "NE is promised 30.7 days and receives in 20.0 — the padding hides the failure."),
    ], size=11, space=3)
    insight_strip(s, "Fixing late delivery is worth more than any marketing campaign: it protects "
                     "4.16 stars and the revenue that depends on them.")

    # --------------------------------------------------- 10 recommendations
    s = blank(prs)
    header(s, "Recommendations", "Ordered by speed of impact per real of effort")
    rows = [
        ("1", "Day-21 second-purchase voucher for the 36,140 New Customers", "≈ R$118k–296k incremental"),
        ("2", "Cut late deliveries 8.1% → 4% in AL, MA, PI, CE", "≈ 4,900 fewer late orders"),
        ("3", "Tighten NE promises to ~20 days (honest SLA)", "no logistics cost, better perception"),
        ("4", "VIP list for 1,886 Champions + Cannot Lose Them", "≈ R$64k + win-back window"),
        ("5", "Bundle Bed Bath Table + Housewares", "+10% AOV ≈ R$230k/year"),
        ("6", "Boleto installments / small discount", "close the 13% AOV gap"),
        ("7", "Prune the long tail; focus top 10 categories", "lower cost, tighter merchandising"),
    ]
    top = Inches(1.35)
    widths = [Inches(0.6), Inches(8.1), Inches(4.1)]
    for i, (n, action, impact) in enumerate(rows):
        y = top + Inches(i * 0.7)
        box = s.shapes.add_shape(5, Inches(0.55), y, Inches(12.3), Inches(0.6))
        box.fill.solid()
        box.fill.fore_color.rgb = WHITE if i % 2 == 0 else RGBColor(0xEE, 0xF3, 0xF7)
        box.line.color.rgb = RGBColor(0xE3, 0xE8, 0xEE)
        box.line.width = Pt(0.5)
        box.shadow.inherit = False
        textbox(s, Inches(0.7), y + Inches(0.1), widths[0], Inches(0.35), n, size=13, bold=True,
                color=PRIMARY)
        textbox(s, Inches(1.25), y + Inches(0.1), widths[1], Inches(0.4), action, size=11.5)
        textbox(s, Inches(9.5), y + Inches(0.1), widths[2], Inches(0.4), impact, size=11,
                color=TEAL, bold=True)
    footer(s, "30 days: activation test · 60 days: carrier SLA + re-promise · 90 days: bundles + boleto + pruning")

    # ------------------------------------------------------- 11 limits/close
    s = blank(prs)
    header(s, "What this analysis cannot say — and what comes next")
    bullets(s, Inches(0.55), Inches(1.4), Inches(6.0), Inches(4.4), [
        ("No cost data —", "revenue is analysed, margin is not."),
        ("No marketing spend —", "CAC, ROAS and channel ROI are out of scope."),
        ("No returns table —", "refunds only visible via canceled/unavailable status."),
        ("Censored horizon —", "partial months excluded; cohorts after 2018-02 are right-censored."),
        ("Snapshot RFM —", "recency scores age with the data."),
    ], size=12, space=10)

    box = s.shapes.add_shape(5, Inches(6.9), Inches(1.4), Inches(5.9), Inches(2.35))
    box.fill.solid()
    box.fill.fore_color.rgb = DEEP
    box.line.fill.background()
    box.shadow.inherit = False
    textbox(s, Inches(7.2), Inches(1.65), Inches(5.3), Inches(0.4), "ONE-LINE ANSWER",
            size=10, bold=True, color=RGBColor(0x8F, 0xC5, 0xD8))
    textbox(s, Inches(7.2), Inches(2.05), Inches(5.3), Inches(1.6),
            "Grow by protecting the 1,886 highest-value customers and by fixing late delivery in the "
            "North-East — not by chasing loyalty in a base that buys once.",
            size=14.5, bold=True, color=WHITE, spacing=1.12)

    plan = [
        ("30 days", "Instrument first-90-day repeat rate; ship the day-21 voucher; define the VIP list."),
        ("60 days", "Carrier SLA for AL/MA/PI/CE; re-promise the North-East; late-order recovery email."),
        ("90 days", "Bundle test; boleto installments; catalogue pruning rules."),
    ]
    for i, (label, text) in enumerate(plan):
        x = Inches(0.55 + i * 4.13)
        c = s.shapes.add_shape(5, x, Inches(4.15), Inches(3.95), Inches(1.35))
        c.fill.solid()
        c.fill.fore_color.rgb = WHITE
        c.line.color.rgb = RGBColor(0xE3, 0xE8, 0xEE)
        c.shadow.inherit = False
        textbox(s, x + Inches(0.18), Inches(4.27), Inches(3.6), Inches(0.3), label.upper(),
                size=10, bold=True, color=PRIMARY)
        textbox(s, x + Inches(0.18), Inches(4.58), Inches(3.6), Inches(0.8), text, size=10.5, color=INK)

    textbox(s, Inches(0.55), Inches(5.75), Inches(12.2), Inches(0.4),
            "Notebook · SQL · Dashboard · Report  —  all reproducible in four commands.",
            size=11, color=MUTED)

    out = REPORTS_DIR / "Olist_Presentation.pptx"
    prs.save(str(out))
    print("wrote", out)
    return out


if __name__ == "__main__":
    build()
