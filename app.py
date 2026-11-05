import hashlib
import html
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from engine.database import load_file_to_sqlite
from engine.llm import generate_sql
from engine.security import UnsafeSQLError

# Cap queries per session to protect the Groq API key on a public demo
MAX_QUERIES = 25
PALETTE = ["#22D3EE", "#818CF8", "#F472B6", "#34D399", "#FBBF24", "#A78BFA"]

st.set_page_config(page_title="Altron SQL", page_icon="🗄️", layout="wide")

# ---------------------------------------------------------------------------
# Styling
# Every text colour is set explicitly, so the UI stays readable even when
# Streamlit's own theme (config.toml) is not applied.
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  color-scheme: dark;
  --ink: #080C1C;
  --deep: #111838;
  --cyan: #22D3EE;
  --indigo: #818CF8;
  --rose: #F472B6;
  --text: #F1F4FF;
  --muted: #B7C0E6;
  --edge: rgba(255,255,255,.20);
  --panel: linear-gradient(145deg, rgba(255,255,255,.13), rgba(255,255,255,.04)), rgba(16,22,56,.62);
  --font: 'Plus Jakarta Sans', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ---------- Base: background and readable text everywhere ---------- */
.stApp {
  font-family: var(--font);
  color: var(--text);
  background:
    radial-gradient(900px 600px at 6% -5%, rgba(99,102,241,.45), transparent 60%),
    radial-gradient(800px 560px at 100% 8%, rgba(34,211,238,.26), transparent 60%),
    radial-gradient(700px 500px at 55% 112%, rgba(244,114,182,.20), transparent 60%),
    linear-gradient(180deg, var(--ink), var(--deep));
  background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stHeader"] * { color: var(--muted) !important; }
.block-container { padding-top: 2.2rem; max-width: 1240px; }

[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] *,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary *,
[data-testid="stText"], [data-testid="stText"] *,
[data-baseweb="select"] *, [data-baseweb="tab"] * { color: var(--text); font-family: var(--font); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }
[data-baseweb="tab"] * { color: var(--muted); }
[data-baseweb="tab"][aria-selected="true"] * { color: #fff; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(22,30,76,.92), rgba(9,13,32,.96));
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
  border-right: 1px solid var(--edge);
}
.brand { display: flex; align-items: center; gap: .8rem; margin: .4rem 0 1.1rem; }
.brand .logo {
  width: 44px; height: 44px; display: grid; place-items: center; font-size: 1.4rem;
  border-radius: 14px; border: 1px solid var(--edge);
  background: linear-gradient(145deg, rgba(34,211,238,.45), rgba(99,102,241,.45));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.4), 0 6px 16px rgba(0,0,0,.35);
}
.brand b { display: block; font-size: 1.25rem; color: #fff; line-height: 1.15; }
.brand span { color: var(--muted); font-size: .85rem; }

/* ---------- Glass panels ---------- */
.glass {
  background: var(--panel);
  border: 1px solid var(--edge);
  border-radius: 22px;
  backdrop-filter: blur(18px) saturate(160%);
  -webkit-backdrop-filter: blur(18px) saturate(160%);
  box-shadow: 0 10px 34px rgba(0,0,0,.40), inset 0 1px 0 rgba(255,255,255,.28);
}
.hero { padding: 1.8rem 2rem; margin-bottom: 1.3rem; }
.hero h1 { margin: 0; font-size: 2.5rem; font-weight: 800; letter-spacing: -0.02em; color: #fff; }
.hero p { margin: .55rem 0 1rem; color: var(--muted); font-size: 1.05rem; line-height: 1.55; max-width: 60ch; }
.badges { display: flex; flex-wrap: wrap; gap: .5rem; }
.badge {
  padding: .3rem .85rem; border-radius: 999px; font-size: .85rem; font-weight: 600; color: #E7FBFF;
  background: rgba(34,211,238,.14); border: 1px solid rgba(34,211,238,.45);
}

.stat { padding: 1rem 1.2rem; }
.stat .v { font-size: 1.75rem; font-weight: 700; line-height: 1.15; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stat .v.small { font-size: 1.15rem; padding: .35rem 0; }
.stat .l { color: var(--muted); font-size: .88rem; margin-top: .25rem; }
.stat.warn .v { color: #FBBF24; }

.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
.step { padding: 1.3rem 1.4rem; }
.step .ic { font-size: 1.5rem; margin-bottom: .5rem; }
.step b { display: block; margin-bottom: .35rem; font-size: 1.08rem; color: #fff; }
.step span { color: var(--muted); font-size: .95rem; line-height: 1.5; }
@media (max-width: 800px) { .steps { grid-template-columns: 1fr; } }

/* ---------- Liquid glass buttons ---------- */
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button {
  position: relative; overflow: hidden; isolation: isolate;
  color: var(--text) !important; font-family: var(--font); font-weight: 600; letter-spacing: .01em;
  padding: .62rem 1.3rem; border-radius: 999px;
  background: linear-gradient(160deg, rgba(255,255,255,.24), rgba(255,255,255,.06));
  border: 1px solid rgba(255,255,255,.32);
  backdrop-filter: blur(14px) saturate(180%);
  -webkit-backdrop-filter: blur(14px) saturate(180%);
  box-shadow: 0 8px 22px rgba(0,0,0,.38), inset 0 1.5px 0 rgba(255,255,255,.6), inset 0 -8px 14px rgba(255,255,255,.06);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button * { color: inherit !important; }
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button::before {
  content: ""; position: absolute; z-index: -1; inset: 1px 8% 52% 8%; border-radius: 999px;
  background: linear-gradient(180deg, rgba(255,255,255,.45), rgba(255,255,255,0));
  opacity: .55; transition: opacity .18s ease;
}
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button::after {
  content: ""; position: absolute; z-index: -1; top: 0; bottom: 0; width: 45%; left: -60%; transform: skewX(-20deg);
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.35), transparent);
  transition: left .6s ease;
}
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button:hover {
  transform: translateY(-2px); border-color: rgba(255,255,255,.55); color: #fff !important;
  box-shadow: 0 14px 30px rgba(34,211,238,.26), 0 8px 22px rgba(0,0,0,.4), inset 0 1.5px 0 rgba(255,255,255,.75), inset 0 -8px 14px rgba(255,255,255,.08);
}
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button:hover::before { opacity: .85; }
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button:hover::after { left: 120%; }
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button:active { transform: translateY(0) scale(.98); }
:is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button:focus-visible { outline: 2px solid var(--cyan); outline-offset: 3px; }

/* Primary action: cyan to indigo tinted glass */
button[kind="primary"], button[kind="primaryFormSubmit"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(160deg, rgba(34,211,238,.75), rgba(99,102,241,.72)) !important;
  border-color: rgba(255,255,255,.5) !important; color: #fff !important;
}

.chips .stButton > button { font-size: .88rem; font-weight: 500; padding: .45rem 1rem; }

/* ---------- Inputs ---------- */
[data-testid="stTextInput"] input {
  background: rgba(8,12,32,.55); color: var(--text) !important; font-family: var(--font);
  border: 1px solid var(--edge); border-radius: 16px; padding: .9rem 1.1rem; font-size: 1rem;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.10);
}
[data-testid="stTextInput"] input::placeholder { color: #8D97C2; opacity: 1; }
[data-testid="stTextInput"] input:focus { border-color: var(--cyan); box-shadow: 0 0 0 3px rgba(34,211,238,.25); }
[data-testid="stTextInput"] > div, [data-baseweb="input"], [data-baseweb="base-input"] { background: transparent !important; }

[data-testid="stFileUploaderDropzone"] {
  background: rgba(8,12,32,.45); border: 1.5px dashed rgba(255,255,255,.38); border-radius: 18px;
}
[data-testid="stFileUploaderDropzone"] *:not(button):not(button *) { color: var(--muted) !important; }
[data-testid="stFileUploaderDropzone"] svg { fill: var(--muted); }
[data-testid="stFileUploaderFile"] * { color: var(--text) !important; }

[data-baseweb="select"] > div { background: rgba(8,12,32,.55); border: 1px solid var(--edge); border-radius: 14px; }
[data-testid="stForm"] { border: none; padding: 0; background: transparent; }

[data-baseweb="tab-list"] {
  gap: .3rem; padding: .3rem; border-radius: 999px; width: fit-content;
  background: rgba(8,12,32,.5); border: 1px solid var(--edge);
}
[data-baseweb="tab"] { border-radius: 999px; padding: .4rem 1.1rem; height: auto; background: transparent; }
[data-baseweb="tab"][aria-selected="true"] { background: rgba(255,255,255,.18); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* ---------- Data, code, alerts, expanders ---------- */
[data-testid="stDataFrame"] { border-radius: 16px; overflow: hidden; border: 1px solid var(--edge); }
code, pre { font-family: 'JetBrains Mono', Consolas, monospace !important; }
[data-testid="stCode"] pre { background: rgba(5,8,22,.75) !important; border: 1px solid var(--edge); border-radius: 16px; }
[data-testid="stAlert"] {
  border-radius: 16px; background: rgba(255,255,255,.09) !important; border: 1px solid var(--edge);
}
[data-testid="stAlert"] * { color: var(--text) !important; }
[data-testid="stExpander"] { border: 1px solid var(--edge); border-radius: 16px; background: rgba(16,22,56,.55); }
[data-testid="stExpander"] details { background: transparent; }
[data-testid="stSpinner"] * { color: var(--text) !important; }

@media (prefers-reduced-motion: reduce) {
  :is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button { transition: none; }
  :is(.stButton, [data-testid="stFormSubmitButton"], [data-testid="stDownloadButton"], [data-testid="stFileUploaderDropzone"]) button::after { display: none; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("file_hash", None)
ss.setdefault("queries", 0)
ss.setdefault("result", None)
ss.setdefault("result_id", 0)
ss.setdefault("question", "")
ss.setdefault("pending", None)
ss.setdefault("history", [])
ss.setdefault("filename", "")
ss.setdefault("row_count", 0)
ss.setdefault("use_demo", False)


def ask(text: str):
    """Callback for chips and history buttons: fill the box and run."""
    ss.question = text
    ss.pending = text


def start_demo():
    ss.use_demo = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def demo_csv() -> bytes:
    """Small built-in dataset so the app can be tried without a file."""
    rng = np.random.default_rng(7)
    n = 240
    dates = pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 330, n), unit="D")
    region = rng.choice(["North", "South", "East", "West"], n)
    region = np.where(rng.random(n) < 0.04, np.char.lower(region.astype(str)), region)  # mixed case
    product = rng.choice(["Laptop", "Phone", "Tablet", "Monitor", "Headset"], n)
    price = pd.Series(product).map({"Laptop": 900, "Phone": 650, "Tablet": 400, "Monitor": 250, "Headset": 90})
    units = rng.integers(1, 20, n)
    sales = (units * price * rng.uniform(0.9, 1.1, n)).round(2)
    df = pd.DataFrame(
        {
            "Order_ID": np.arange(1001, 1001 + n),
            "Order_Date": dates.strftime("%Y-%m-%d"),
            "Region": region,
            "Product": product,
            "Units": units,
            "Sales": sales,
        }
    ).sort_values("Order_Date")
    df.loc[df.sample(3, random_state=1).index, "Sales"] = np.nan  # a few NULLs
    return df.to_csv(index=False).encode("utf-8")


def looks_like_date(series: pd.Series) -> bool:
    if series.dtype.kind in "iufb":
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return bool(pd.to_datetime(series, errors="coerce").notna().all())


def default_kind(df: pd.DataFrame, x: str) -> str:
    return "Line" if looks_like_date(df[x]) or "date" in x.lower() else "Bar"


def build_chart(df: pd.DataFrame, kind: str, x: str, y: str):
    common = {"color_discrete_sequence": PALETTE}
    if kind == "Bar":
        fig = px.bar(df, x=x, y=y, **common)
    elif kind == "Line":
        fig = px.line(df, x=x, y=y, markers=True, **common)
    elif kind == "Area":
        fig = px.area(df, x=x, y=y, **common)
    elif kind == "Scatter":
        fig = px.scatter(df, x=x, y=y, **common)
    else:
        fig = px.pie(df, names=x, values=y, hole=0.55, **common)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Plus Jakarta Sans, Segoe UI, sans-serif", "color": "#F1F4FF", "size": 13},
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        height=440,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.08)", zeroline=False)
    if kind == "Bar":
        fig.update_traces(marker_line_width=0)
    return fig


def suggestions(preview: pd.DataFrame) -> list[str]:
    nums = [c for c in preview.select_dtypes("number").columns if not c.lower().endswith("id")]
    cats_all = list(preview.select_dtypes(exclude="number").columns)
    cats = [
        c for c in cats_all
        if preview[c].nunique() < len(preview) and "date" not in c.lower()
    ] or cats_all
    out = ["How many rows are there?"]
    if nums:
        pref = ("sales", "revenue", "amount", "price", "salary", "total")
        num = next((c for c in nums if any(p in c.lower() for p in pref)), nums[0])
        if cats:
            out.append(f"What is the average {num} by {cats[0]}?")
            out.append(f"Show the top 5 {cats[0]} by total {num}")
        else:
            out.append(f"What is the average {num}?")
    return out


def stat(value, label, warn=False, small=False):
    cls = "glass stat warn" if warn else "glass stat"
    vcls = "v small" if small else "v"
    return (
        f'<div class="{cls}"><div class="{vcls}">{html.escape(str(value))}</div>'
        f'<div class="l">{html.escape(label)}</div></div>'
    )


def execute(q: str):
    if ss.queries >= MAX_QUERIES:
        st.warning("You have reached the query limit for this session. Refresh the page to start over.")
        return
    ss.queries += 1
    with st.spinner("Writing and checking your SQL..."):
        try:
            ss.result = generate_sql(q, ss.schema, ss.conn)
            ss.result_id += 1
            ss.history = [q] + [h for h in ss.history if h != q][:5]
        except UnsafeSQLError as e:
            ss.result = None
            st.error(f"🚨 Blocked by the security layer: {e}")
        except Exception as e:
            ss.result = None
            st.error(f"The query could not be completed: {e}")


def load_source(data: bytes, name: str):
    h = hashlib.sha256(data).hexdigest()
    if h == ss.file_hash:  # reload only when the data changes
        return
    try:
        ss.conn, ss.schema, ss.preview = load_file_to_sqlite(data, name)
        ss.row_count = ss.conn.execute("SELECT COUNT(*) FROM user_data").fetchone()[0]
        ss.file_hash, ss.filename, ss.result, ss.history = h, name, None, []
    except Exception as e:
        st.error(f"Could not load this file: {e}")
        st.stop()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="logo">🗄️</div>'
        "<div><b>Altron SQL</b><span>Ask your data anything</span></div></div>",
        unsafe_allow_html=True,
    )
    up = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx"])

    if up:
        load_source(up.getvalue(), up.name)
    elif ss.use_demo:
        load_source(demo_csv(), "demo_sales.csv")
    else:
        st.button("Try demo data", on_click=start_demo, use_container_width=True)

    if ss.file_hash:
        st.success(f"Loaded {ss.filename}")
        with st.expander("Schema sent to the model"):
            st.text(ss.schema)
        st.caption("Privacy: the schema and sample values are sent to Groq.")

    if ss.history:
        st.markdown("**Recent questions**")
        for i, past in enumerate(ss.history):
            st.button(past, key=f"hist_{i}", on_click=ask, args=(past,), use_container_width=True)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="glass hero">
      <h1>Altron SQL</h1>
      <p>Upload a spreadsheet, ask a question in plain English, and get a checked, read-only SQL query with a table and a chart.</p>
      <div class="badges">
        <span class="badge">Read-only queries</span>
        <span class="badge">Validated before running</span>
        <span class="badge">Fixes its own errors</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not ss.file_hash:
    st.markdown(
        """
        <div class="steps">
          <div class="glass step"><div class="ic">📂</div><b>Upload your data</b><span>Drop a CSV or Excel file in the sidebar, or try the demo data. It stays in memory for this session.</span></div>
          <div class="glass step"><div class="ic">💬</div><b>Ask in plain English</b><span>Pick a suggested question or write your own, such as the top 5 sales by region.</span></div>
          <div class="glass step"><div class="ic">📊</div><b>Review and export</b><span>Check the SQL, explore the chart, and download the result as CSV.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

remaining = MAX_QUERIES - ss.queries
c1, c2, c3, c4 = st.columns(4)
c1.markdown(stat(f"{ss.row_count:,}", "Rows"), unsafe_allow_html=True)
c2.markdown(stat(len(ss.preview.columns), "Columns"), unsafe_allow_html=True)
c3.markdown(stat(ss.filename, "File", small=True), unsafe_allow_html=True)
c4.markdown(stat(remaining, "Questions left this session", warn=remaining <= 5), unsafe_allow_html=True)

st.write("")
with st.expander("Preview the first 10 rows"):
    st.dataframe(ss.preview, use_container_width=True)

st.markdown("**Try a question**")
st.markdown('<div class="chips">', unsafe_allow_html=True)
chip_cols = st.columns(3)
for i, s in enumerate(suggestions(ss.preview)):
    chip_cols[i % 3].button(s, key=f"chip_{i}", on_click=ask, args=(s,), use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.write("")
with st.form("ask_form", clear_on_submit=False):
    q = st.text_input(
        "Your question",
        key="question",
        placeholder="e.g., Show me the top 5 sales by region",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Run query", type="primary")

if submitted and q.strip():
    ss.pending = q.strip()

if ss.pending:
    pending, ss.pending = ss.pending, None
    execute(pending)

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
r = ss.result
if r:
    st.write("")
    summary = f"{len(r.df):,} row{'s' if len(r.df) != 1 else ''} returned"
    if len(r.attempts) > 1:
        summary += f" after {len(r.attempts) - 1} automatic fix{'es' if len(r.attempts) > 2 else ''}"
    st.markdown(f"**{summary}**")
    if r.truncated:
        st.warning("Showing the first 1,000 rows. Add a filter or a LIMIT to narrow the result.")

    nums = list(r.df.select_dtypes("number").columns)
    can_chart = len(r.df) >= 2 and len(nums) > 0 and len(r.df.columns) >= 2

    t_table, t_chart, t_sql, t_trace = st.tabs(["📋 Table", "📈 Chart", "🧾 SQL", "🔧 Self-healing"])

    with t_table:
        st.dataframe(r.df, use_container_width=True)
        st.download_button("Download CSV", r.df.to_csv(index=False), "result.csv", "text/csv")

    with t_chart:
        if not can_chart:
            st.info("A chart needs at least two rows and one numeric column. Try a question that groups or ranks the data.")
        else:
            rid = ss.result_id
            cols = list(r.df.columns)
            non_num = [c for c in cols if c not in nums]
            default_x = non_num[0] if non_num else cols[0]
            default_y = next((c for c in nums if not c.lower().endswith("id") and c != default_x), nums[0])
            kinds = ["Bar", "Line", "Area", "Scatter", "Pie"]

            k1, k2, k3 = st.columns(3)
            x = k1.selectbox("X axis", cols, index=cols.index(default_x), key=f"x_{rid}")
            y = k2.selectbox("Y axis", nums, index=nums.index(default_y), key=f"y_{rid}")
            kind = k3.selectbox("Chart type", kinds, index=kinds.index(default_kind(r.df, x)), key=f"k_{rid}")

            chart_df = r.df.head(200)
            if len(r.df) > 200:
                st.caption("Charting the first 200 rows.")
            if kind == "Pie" and len(chart_df) > 12:
                st.caption("Pie charts read best with 12 slices or fewer. Consider a bar chart.")
            st.plotly_chart(build_chart(chart_df, kind, x, y), use_container_width=True)

    with t_sql:
        st.code(r.sql, language="sql")
        st.caption("Validated as a single read-only statement before it ran.")

    with t_trace:
        if len(r.attempts) > 1:
            st.write("The first query failed, so the error was sent back to the model for a fix.")
            for n, a in enumerate(r.attempts, 1):
                st.markdown(f"**Attempt {n}** " + ("✅ succeeded" if not a["error"] else "❌ failed"))
                st.code(a["sql"], language="sql")
                if a["error"]:
                    st.caption(f"SQLite error: {a['error']}")
        else:
            st.success("The first query worked, so no fixes were needed.")