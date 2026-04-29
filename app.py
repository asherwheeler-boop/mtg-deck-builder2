import streamlit as st
import requests
import time
import anthropic
import re
import json
import plotly.express as px
import plotly.graph_objects as go

# ═══════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════
st.set_page_config(page_title="MTG AI Deck Builder", page_icon="🐉", layout="wide")

st.markdown("""
<style>
    .main-title {text-align:center;font-size:2.5rem;font-weight:bold;margin-bottom:0;}
    .sub-title {text-align:center;font-size:1.1rem;color:#888;margin-top:0;}
    .stButton>button {width:100%;}
    div[data-testid="stHorizontalBlock"] .stButton>button {
        background-color:#6C3483;color:white;font-weight:bold;font-size:0.85rem;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">🐉 MTG AI Deck Builder 🧙‍♂️</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Build · Upgrade · Compare · Dominate</p>', unsafe_allow_html=True)
st.markdown("---")

# ═══════════════════════════════════════════════
# SESSION STATE INIT
# ═══════════════════════════════════════════════
defaults = {
    "deck_result": None, "card_images": {}, "selected_card": None,
    "show_config": False, "saved_decks": {}, "deck_card_data": {},
    "sideboard_result": None, "matchup_result": None, "swap_result": None,
    "upgrade_result": None, "recommend_result": None, "curated_commanders": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Deck Settings")
    st.markdown("---")

    platform = st.radio("🎮 Platform", ["Paper (Tabletop)", "MTG Arena (Digital)"],
        help="Paper uses real-world meta. Arena uses digital-specific meta.")
    is_arena = platform == "MTG Arena (Digital)"
    st.markdown("---")

    st.subheader("🎨 Color Identity")
    cw, cu = st.columns(2)
    cb, cr = st.columns(2)
    cg, _ = st.columns(2)
    with cw: white = st.checkbox("⚪ White")
    with cu: blue = st.checkbox("🔵 Blue")
    with cb: black = st.checkbox("⚫ Black")
    with cr: red = st.checkbox("🔴 Red")
    with cg: green = st.checkbox("🟢 Green")

    selected_colors = []
    if white: selected_colors.append("W")
    if blue:  selected_colors.append("U")
    if black: selected_colors.append("B")
    if red:   selected_colors.append("R")
    if green: selected_colors.append("G")
    color_identity = "".join(selected_colors)
    st.markdown("---")

    creature_type = st.text_input("🦎 Creature / Card Type (optional)",
        placeholder="e.g., Dragons, Wizards, Elves...")
    format_choice_sidebar = st.selectbox("📜 Format",
        ["Commander", "Modern", "Standard", "Pioneer", "Pauper"])
    strategy_sidebar = st.selectbox("🎯 Strategy",
        ["Aggressive", "Midrange", "Control", "Combo"])
    budget = st.selectbox("💰 Budget",
        ["No Limit", "Budget ($50 or less)", "Mid-range ($50–$150)"])
    st.markdown("---")
    build_custom_button = st.button("🚀 Build Custom Deck", use_container_width=True)
    st.caption("Build a tribal/color deck without picking a card from the grid.")

    # Saved Decks in sidebar
    st.markdown("---")
    with st.expander("📂 Saved Decks"):
        if st.session_state.saved_decks:
            for name in list(st.session_state.saved_decks.keys()):
                col_load, col_del = st.columns([3, 1])
                with col_load:
                    if st.button(f"📄 {name}", key=f"load_{name}", use_container_width=True):
                        st.session_state.deck_result = st.session_state.saved_decks[name]
                        st.session_state.show_config = False
                        st.session_state.deck_card_data = {}
                        st.rerun()
                with col_del:
                    if st.button("🗑️", key=f"del_{name}"):
                        del st.session_state.saved_decks[name]
                        st.rerun()
        else:
            st.caption("No saved decks yet.")

# ═══════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════
def normalize_creature_type(raw):
    text = raw.strip().lower()
    irregulars = {"wolves":"wolf","werewolves":"werewolf","elves":"elf",
        "dwarves":"dwarf","fungi":"fungus","sphinxes":"sphinx","cyclopes":"cyclops"}
    if text in irregulars: return irregulars[text]
    if text.endswith("s") and len(text) > 3: return text[:-1]
    return text

def parse_decklist(text):
    """Parse decklist text and return list of {quantity, name}."""
    cards = []
    seen = set()
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r'^[-•*]?\s*(\d+)\s*[xX]?\s+(.+)$', line)
        if m:
            qty = int(m.group(1))
            name = m.group(2).strip()
            name = re.sub(r'\s*[\(\[].*$', '', name)
            if name and name.lower() not in seen and name.lower() != "none":
                cards.append({"quantity": qty, "name": name})
                seen.add(name.lower())
    return cards

def fetch_deck_cards(card_names):
    """Fetch card data from Scryfall Collection API. Returns dict of name->data."""
    results = {}
    batches = [card_names[i:i+75] for i in range(0, len(card_names), 75)]
    for batch in batches:
        identifiers = [{"name": n} for n in batch]
        try:
            resp = requests.post("https://api.scryfall.com/cards/collection",
                json={"identifiers": identifiers})
            if resp.status_code == 200:
                data = resp.json()
                for card in data.get("data", []):
                    results[card["name"].lower()] = card
            time.sleep(0.1)
        except:
            pass
    return results

def get_card_cmc(card_data): return card_data.get("cmc", 0)

def get_card_price(card_data):
    try:
        p = card_data.get("prices", {}).get("usd")
        return float(p) if p else 0.0
    except: return 0.0

def get_card_colors(card_data): return card_data.get("colors", [])

def get_card_image(card_data):
    if "image_uris" in card_data: return card_data["image_uris"].get("normal")
    elif "card_faces" in card_data and len(card_data["card_faces"]) > 0:
        face = card_data["card_faces"][0]
        if "image_uris" in face: return face["image_uris"].get("normal")
    return None

def get_card_type(card_data): return card_data.get("type_line", "")

def call_claude(system_prompt, user_prompt, max_tokens=4000):
    """Generic Claude API call."""
    try:
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens, temperature=0.7,
            system=system_prompt, messages=[{"role": "user", "content": user_prompt}])
        return response.content[0].text
    except Exception as e:
        st.error(f"❌ Claude API Error: {e}\n\n"
            "**Make sure your ANTHROPIC_API_KEY is set in Streamlit secrets.**")
        return None

# ═══════════════════════════════════════════════
# SCRYFALL SEARCH
# ═══════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_popular_cards(color_filter="", arena_only=False):
    query = "t:legendary t:creature f:commander"
    if color_filter: query += f" id<={color_filter}"
    if arena_only: query += " game:arena"
    url = "https://api.scryfall.com/cards/search"
    params = {"q": query, "order": "edhrec", "unique": "cards"}
    cards = []
    try:
        response = requests.get(url, params=params)
        if response.status_code == 404: return []
        response.raise_for_status()
        data = response.json()
        for card in data.get("data", [])[:24]:
            image_url = None
            if "image_uris" in card: image_url = card["image_uris"].get("normal")
            elif "card_faces" in card and len(card["card_faces"]) > 0:
                face = card["card_faces"][0]
                if "image_uris" in face: image_url = face["image_uris"].get("normal")
            oracle = card.get("oracle_text", "")
            if not oracle and "card_faces" in card:
                oracle = " // ".join(f.get("oracle_text", "") for f in card["card_faces"])
            color_map = {"W":"⚪","U":"🔵","B":"⚫","R":"🔴","G":"🟢"}
            ci = card.get("color_identity", [])
            color_symbols = " ".join(color_map.get(c, c) for c in ci) if ci else "Colorless"
            cards.append({"name": card.get("name","Unknown"), "mana_cost": card.get("mana_cost",""),
                "cmc": card.get("cmc",0), "type_line": card.get("type_line",""),
                "oracle_text": oracle, "color_identity": ci, "color_symbols": color_symbols,
                "rarity": card.get("rarity",""),
                "price_usd": card.get("prices",{}).get("usd","N/A"),
                "image_url": image_url, "set_name": card.get("set_name","")})
    except: pass
    return cards

def fetch_curated_commanders(color_filter="", is_arena=False):
    """Ask Claude for 24 popular/meta commanders, then fetch each from Scryfall."""
    color_note = ""
    if color_filter:
        color_map = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        color_names = [color_map.get(c, c) for c in color_filter]
        color_note = f"\nIMPORTANT: Only suggest commanders whose color identity fits within: {', '.join(color_names)}. Commanders can use fewer colors but CANNOT use colors outside this list."

    platform_note = "MTG Arena (only Arena-legal commanders)" if is_arena else "Paper (all legal commanders)"

    system_prompt = ("You are an expert MTG Commander player who follows the competitive "
        "and casual meta closely. You know which commanders are popular on EDHREC, "
        "which are winning tournaments, and which are community favorites.")

    user_prompt = (f"List exactly 24 legendary creatures that are great commanders right now for {platform_note}.\n"
        f"{color_note}\n\n"
        "Include a MIX of:\n"
        "- 8 currently meta/competitive commanders (cEDH or high-power)\n"
        "- 8 popular community favorites (most-played on EDHREC)\n"
        "- 8 fun/unique commanders that are powerful but less common\n\n"
        "RESPOND WITH ONLY a numbered list of card names, nothing else. Example:\n"
        "1. Atraxa, Praetors' Voice\n"
        "2. Korvold, Fae-Cursed King\n"
        "...\n")

    result = call_claude(system_prompt, user_prompt, 1000)
    if not result:
        return []

    # Parse commander names from Claude's response
    names = re.findall(r'\d+\.\s*(.+)', result)
    if not names:
        return []

    # Fetch each commander from Scryfall
    commanders = []
    for name in names[:24]:
        clean_name = name.strip().rstrip("*").strip()
        try:
            resp = requests.get("https://api.scryfall.com/cards/named",
                params={"fuzzy": clean_name})
            if resp.status_code == 200:
                card = resp.json()
                image_url = None
                if "image_uris" in card:
                    image_url = card["image_uris"].get("normal")
                elif "card_faces" in card and len(card["card_faces"]) > 0:
                    face = card["card_faces"][0]
                    if "image_uris" in face:
                        image_url = face["image_uris"].get("normal")
                oracle = card.get("oracle_text", "")
                if not oracle and "card_faces" in card:
                    oracle = " // ".join(f.get("oracle_text", "") for f in card["card_faces"])
                color_map = {"W":"⚪","U":"🔵","B":"⚫","R":"🔴","G":"🟢"}
                ci = card.get("color_identity", [])
                color_symbols = " ".join(color_map.get(c, c) for c in ci) if ci else "Colorless"
                commanders.append({
                    "name": card.get("name","Unknown"),
                    "mana_cost": card.get("mana_cost",""),
                    "cmc": card.get("cmc",0),
                    "type_line": card.get("type_line",""),
                    "oracle_text": oracle,
                    "color_identity": ci,
                    "color_symbols": color_symbols,
                    "rarity": card.get("rarity",""),
                    "price_usd": card.get("prices",{}).get("usd","N/A"),
                    "image_url": image_url,
                    "set_name": card.get("set_name",""),
                })
            time.sleep(0.1)  # Respect Scryfall rate limits
        except:
            pass

    return commanders

def search_scryfall(creature_type, format_choice, color_filter="", arena_only=False):
    fmt = format_choice.lower()
    parts = []
    if creature_type.strip():
        singular = normalize_creature_type(creature_type)
        parts.append(f"(t:{singular} OR o:{singular})")
    parts.append(f"f:{fmt}")
    if color_filter: parts.append(f"id<={color_filter}")
    if arena_only: parts.append("game:arena")
    query = " ".join(parts)
    st.info(f"🔍 Searching Scryfall: `{query}`")
    url = "https://api.scryfall.com/cards/search"
    params = {"q": query, "order": "edhrec", "unique": "cards"}
    all_cards = []
    try:
        while url and len(all_cards) < 300:
            response = requests.get(url, params=params)
            if response.status_code == 404: return []
            response.raise_for_status()
            data = response.json()
            for card in data.get("data", []):
                image_url = None
                if "image_uris" in card: image_url = card["image_uris"].get("normal")
                elif "card_faces" in card and len(card["card_faces"]) > 0:
                    face = card["card_faces"][0]
                    if "image_uris" in face: image_url = face["image_uris"].get("normal")
                oracle = card.get("oracle_text", "")
                if not oracle and "card_faces" in card:
                    oracle = " // ".join(f.get("oracle_text","") for f in card["card_faces"])
                all_cards.append({"name": card.get("name","Unknown"),
                    "mana_cost": card.get("mana_cost",""), "cmc": card.get("cmc",0),
                    "type_line": card.get("type_line",""), "oracle_text": oracle,
                    "colors": card.get("colors",[]),
                    "color_identity": card.get("color_identity",[]),
                    "rarity": card.get("rarity",""),
                    "price_usd": card.get("prices",{}).get("usd","N/A"),
                    "image_url": image_url, "set_name": card.get("set_name","")})
            if data.get("has_more"):
                url = data.get("next_page"); params = {}; time.sleep(0.1)
            else: break
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Scryfall Error: {e}"); return []
    return all_cards

def format_card_data(cards):
    lines = []
    for c in cards:
        price_str = f"${c['price_usd']}" if c['price_usd'] != "N/A" else "N/A"
        lines.append(f"- {c['name']} | {c['mana_cost']} | {c['type_line']} | "
            f"{c['oracle_text'][:150]} | Price: {price_str}")
    return "\n".join(lines)

# ═══════════════════════════════════════════════
# AI DECK BUILDER
# ═══════════════════════════════════════════════
def build_deck_with_ai(card_text, creature_type, format_choice, strategy, budget,
                       platform, card_name=None, card_info=None):
    is_commander = format_choice == "Commander"
    deck_size = 100 if is_commander else 60
    if platform == "MTG Arena (Digital)":
        platform_note = ("**PLATFORM: MTG Arena**\n- Only Arena-available cards.\n"
            "- Arena meta and ladder decks.\n- Mention wildcard costs.\n")
    else:
        platform_note = ("**PLATFORM: Paper**\n- Real-world tournament meta.\n"
            "- Consider card prices.\n")
    card_note = ""
    if card_name:
        if is_commander:
            card_note = (f"- Commander: **{card_name}**.\n- Details: {card_info}\n"
                f"- Exactly 100 cards including commander.\n- Match commander's color identity.\n")
        else:
            card_note = (f"- Build around **{card_name}** as key card.\n- Details: {card_info}\n"
                f"- Up to 4 copies of {card_name}.\n- Deck size: {deck_size} cards.\n")
    elif is_commander:
        card_note = ("- Pick the BEST commander and list it at top.\n"
            "- Exactly 100 cards.\n- Match commander's color identity.\n")
    tribal_note = f"**{creature_type}** tribal theme." if creature_type.strip() else ""
    if is_commander:
        cmd_section = "## 👑 Commander\n- [Commander Name]\n"
    else:
        cmd_section = "## ⭐ Build-Around Card\n- [Card Name] (x4 or as appropriate)\n"

    system_prompt = ("You are an expert MTG deck builder with deep knowledge of competitive "
        "meta for paper and Arena, card synergies, mana curves, and strategies across all formats.")
    user_prompt = f"""Build me a {format_choice} deck.
{tribal_note}
{platform_note}
**Strategy:** {strategy}
**Budget:** {budget}
**Deck Size:** {deck_size} cards
{card_note}

Relevant legal cards:
{card_text}

**INSTRUCTIONS:**
1. Use cards from the list as core.
2. Include essential staples NOT on the list — lands, removal, ramp, card draw.
3. Smooth mana curve, competitive and playable.
4. Consider current {platform} meta.

**FORMAT RESPONSE EXACTLY LIKE THIS:**

{cmd_section}
## 🗡️ Decklist

### Creatures (X)
- 1x Card Name

### Instants (X)
- 1x Card Name

### Sorceries (X)
- 1x Card Name

### Enchantments (X)
- 1x Card Name

### Artifacts (X)
- 1x Card Name

### Planeswalkers (X)
- 1x Card Name

### Lands (X)
- 1x Card Name

## 🧠 Strategy Explanation
[2-3 paragraphs on game plan and piloting. Include platform-specific tips.]

## 🔗 Key Synergies
- [Synergy 1: Card A + Card B — explanation]
- [Synergy 2: Card C + Card D — explanation]
- [Synergy 3: etc.]
"""
    return call_claude(system_prompt, user_prompt)

# ═══════════════════════════════════════════════
# DECK ANALYTICS (mana curve, price, color pie)
# ═══════════════════════════════════════════════
def show_deck_analytics(deck_text):
    parsed = parse_decklist(deck_text)
    if not parsed:
        st.warning("Could not parse decklist for analytics.")
        return

    card_names = [c["name"] for c in parsed]
    if not st.session_state.deck_card_data:
        with st.spinner("📊 Fetching card data for analytics..."):
            st.session_state.deck_card_data = fetch_deck_cards(card_names)
    card_data = st.session_state.deck_card_data

    # ── PRICE METRICS ──
    st.markdown("### 💰 Deck Price Estimate")
    total_price = 0
    card_prices = []
    for c in parsed:
        data = card_data.get(c["name"].lower(), {})
        price = get_card_price(data) * c["quantity"]
        total_price += price
        if get_card_price(data) > 0:
            card_prices.append({"name": c["name"], "price": get_card_price(data), "qty": c["quantity"]})

    card_prices.sort(key=lambda x: x["price"], reverse=True)
    most_exp = card_prices[0] if card_prices else {"name": "N/A", "price": 0}
    cheapest = card_prices[-1] if card_prices else {"name": "N/A", "price": 0}
    avg_price = total_price / max(len(card_prices), 1)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Total Price", f"${total_price:.2f}")
    p2.metric("Most Expensive", f"${most_exp['price']:.2f}", most_exp["name"])
    p3.metric("Average Card", f"${avg_price:.2f}")
    p4.metric("Cheapest", f"${cheapest['price']:.2f}", cheapest["name"])

    # ── MANA CURVE ──
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("### 📊 Mana Curve")
        cmc_counts = {i: 0 for i in range(8)}
        for c in parsed:
            data = card_data.get(c["name"].lower(), {})
            cmc = int(get_card_cmc(data))
            type_line = get_card_type(data).lower()
            if "land" in type_line: continue
            bucket = min(cmc, 7)
            cmc_counts[bucket] += c["quantity"]
        labels = ["0", "1", "2", "3", "4", "5", "6", "7+"]
        values = [cmc_counts[i] for i in range(8)]
        fig = go.Figure(go.Bar(x=labels, y=values,
            marker_color="#6C3483", text=values, textposition="auto"))
        fig.update_layout(xaxis_title="Mana Value", yaxis_title="Card Count",
            height=350, margin=dict(l=20, r=20, t=20, b=40))
        st.plotly_chart(fig, use_container_width=True)

    # ── COLOR PIE ──
    with chart_col2:
        st.markdown("### 🎨 Color Breakdown")
        color_counts = {"White": 0, "Blue": 0, "Black": 0, "Red": 0,
                        "Green": 0, "Colorless": 0, "Multicolor": 0}
        color_map_full = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        for c in parsed:
            data = card_data.get(c["name"].lower(), {})
            colors = get_card_colors(data)
            type_line = get_card_type(data).lower()
            if "land" in type_line: continue
            if len(colors) > 1: color_counts["Multicolor"] += c["quantity"]
            elif len(colors) == 1: color_counts[color_map_full.get(colors[0], "Colorless")] += c["quantity"]
            else: color_counts["Colorless"] += c["quantity"]

        pie_colors = {"White":"#F9FAF4","Blue":"#0E68AB","Black":"#150B00",
            "Red":"#D3202A","Green":"#00733E","Colorless":"#CDC5BF","Multicolor":"#CFB53B"}
        filtered = {k: v for k, v in color_counts.items() if v > 0}
        if filtered:
            fig2 = go.Figure(go.Pie(labels=list(filtered.keys()), values=list(filtered.values()),
                marker=dict(colors=[pie_colors[k] for k in filtered.keys()]),
                textinfo="label+value+percent", hole=0.3))
            fig2.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig2, use_container_width=True)

    # ── TYPE BREAKDOWN ──
    st.markdown("### 📋 Card Type Breakdown")
    type_counts = {"Creatures": 0, "Instants": 0, "Sorceries": 0,
        "Enchantments": 0, "Artifacts": 0, "Planeswalkers": 0, "Lands": 0, "Other": 0}
    for c in parsed:
        data = card_data.get(c["name"].lower(), {})
        tl = get_card_type(data).lower()
        if "creature" in tl: type_counts["Creatures"] += c["quantity"]
        elif "instant" in tl: type_counts["Instants"] += c["quantity"]
        elif "sorcery" in tl: type_counts["Sorceries"] += c["quantity"]
        elif "enchantment" in tl: type_counts["Enchantments"] += c["quantity"]
        elif "artifact" in tl: type_counts["Artifacts"] += c["quantity"]
        elif "planeswalker" in tl: type_counts["Planeswalkers"] += c["quantity"]
        elif "land" in tl: type_counts["Lands"] += c["quantity"]
        else: type_counts["Other"] += c["quantity"]

    type_filtered = {k: v for k, v in type_counts.items() if v > 0}
    if type_filtered:
        tc = st.columns(len(type_filtered))
        for i, (typ, cnt) in enumerate(type_filtered.items()):
            tc[i].metric(typ, cnt)

# ═══════════════════════════════════════════════
# EXPORT FORMATS
# ═══════════════════════════════════════════════
def show_export_options(deck_text):
    parsed = parse_decklist(deck_text)
    if not parsed: return

    with st.expander("📤 Export Deck"):
        tab_arena, tab_mox, tab_mtgo, tab_txt = st.tabs(
            ["Arena", "Moxfield", "MTGO", "Plain Text"])

        arena_lines = []
        for c in parsed:
            arena_lines.append(f"{c['quantity']} {c['name']}")
        arena_text = "\n".join(arena_lines)

        with tab_arena:
            st.markdown("**Copy and paste directly into MTG Arena:**")
            st.code(arena_text, language=None)
        with tab_mox:
            st.markdown("**Moxfield import format:**")
            st.code(arena_text, language=None)
        with tab_mtgo:
            st.markdown("**MTGO import format:**")
            st.code(arena_text, language=None)
        with tab_txt:
            st.markdown("**Full decklist with AI notes:**")
            st.code(deck_text, language=None)

# ═══════════════════════════════════════════════
# VISUAL DECKLIST (card images)
# ═══════════════════════════════════════════════
def show_visual_decklist(deck_text):
    parsed = parse_decklist(deck_text)
    if not parsed: return
    card_data = st.session_state.deck_card_data

    with st.expander("🔍 Visual Decklist — Card Images"):
        images = []
        for c in parsed:
            data = card_data.get(c["name"].lower(), {})
            img = get_card_image(data)
            if img:
                images.append({"name": c["name"], "url": img, "qty": c["quantity"]})
        if images:
            cols = st.columns(5)
            for idx, card in enumerate(images):
                with cols[idx % 5]:
                    st.image(card["url"], caption=f"{card['qty']}x {card['name']}",
                        use_container_width=True)
        else:
            st.caption("No card images found.")

# ═══════════════════════════════════════════════
# CARD SWAP TOOL
# ═══════════════════════════════════════════════
def show_swap_tool(deck_text):
    parsed = parse_decklist(deck_text)
    if not parsed: return

    st.markdown("### 🔄 Card Swap Tool")
    card_names = [c["name"] for c in parsed]
    swap_card = st.selectbox("Select a card to replace:", card_names, key="swap_select")
    swap_reason = st.text_input("Why? (optional)", placeholder="e.g., Too expensive, I don't own it...",
        key="swap_reason")

    if st.button("💡 Suggest Replacement", key="swap_btn"):
        reason = f" Reason: {swap_reason}" if swap_reason else ""
        prompt = (f"In this MTG decklist:\n\n{deck_text}\n\n"
            f"Suggest the single best replacement for **{swap_card}**.{reason}\n\n"
            "Respond with:\n## Swap: [Old Card] → [New Card]\n"
            "**Why:** [1-2 sentence explanation]\n"
            "**Synergy:** [How it fits the deck strategy]")
        with st.spinner("Thinking..."):
            result = call_claude("You are an expert MTG deck builder.", prompt, 500)
        if result:
            st.session_state.swap_result = result

    if st.session_state.swap_result:
        st.markdown(st.session_state.swap_result)

# ═══════════════════════════════════════════════
# SIDEBOARD GENERATOR
# ═══════════════════════════════════════════════
def show_sideboard_gen(deck_text, format_choice):
    if format_choice == "Commander": return

    st.markdown("### 📋 Sideboard Generator")
    if st.button("Generate 15-Card Sideboard", key="side_btn"):
        prompt = (f"Here is my {format_choice} decklist:\n\n{deck_text}\n\n"
            f"Generate a 15-card sideboard for {format_choice}. For each card explain "
            "which matchup it's for. Format:\n\n## Sideboard (15)\n"
            "- Nx Card Name — *vs [Matchup]: explanation*\n")
        with st.spinner("Building sideboard..."):
            result = call_claude("You are an expert MTG deck builder specializing in "
                "sideboard construction.", prompt, 1500)
        if result:
            st.session_state.sideboard_result = result

    if st.session_state.sideboard_result:
        st.markdown(st.session_state.sideboard_result)

# ═══════════════════════════════════════════════
# MATCHUP ANALYSIS
# ═══════════════════════════════════════════════
def show_matchup_analysis(deck_text):
    st.markdown("### ⚔️ Matchup Analysis")
    if st.button("Analyze Matchups", key="matchup_btn"):
        prompt = (f"Analyze this MTG decklist:\n\n{deck_text}\n\n"
            "Provide:\n## ✅ Favorable Matchups\n- [Deck archetype]: why we win\n\n"
            "## ❌ Unfavorable Matchups\n- [Deck archetype]: why we struggle\n\n"
            "## 🤝 Even Matchups\n- [Deck archetype]: how the game usually goes\n\n"
            "## 🃏 Mulligan Guide\n- What hands to keep vs aggro, control, combo\n\n"
            "## 💡 General Tips\n- 3-5 tips for piloting this deck well")
        with st.spinner("Analyzing matchups..."):
            result = call_claude("You are an expert MTG competitive analyst.", prompt, 2000)
        if result:
            st.session_state.matchup_result = result

    if st.session_state.matchup_result:
        st.markdown(st.session_state.matchup_result)

# ═══════════════════════════════════════════════
# CORE BUILD LOGIC
# ═══════════════════════════════════════════════
def run_deck_build(selected_card=None, format_override=None, strategy_override=None):
    fmt = format_override or format_choice_sidebar
    strat = strategy_override or strategy_sidebar
    card_name, card_info, search_color = None, None, color_identity

    if selected_card:
        card_name = selected_card["name"]
        card_info = (f"{selected_card['name']} | {selected_card['mana_cost']} | "
            f"{selected_card['type_line']} | {selected_card['oracle_text']}")
        search_color = "".join(selected_card["color_identity"])

    with st.spinner("🔍 Searching for cards..."):
        cards = search_scryfall(creature_type, fmt, search_color, is_arena)
    if not cards:
        st.warning("⚠️ No cards found. Try different colors, format, or creature type.")
        return
    st.success(f"✅ Found **{len(cards)}** cards! Sending to Claude...")
    st.session_state.card_images = {c["name"]: c["image_url"] for c in cards if c["image_url"]}
    card_text = format_card_data(cards)

    with st.spinner("🤖 Claude is building your deck... 15–30 seconds."):
        result = build_deck_with_ai(card_text, creature_type, fmt, strat, budget,
            platform, card_name=card_name, card_info=card_info)
    if result:
        st.session_state.deck_result = result
        st.session_state.deck_card_data = {}
        st.session_state.sideboard_result = None
        st.session_state.matchup_result = None
        st.session_state.swap_result = None

# ═══════════════════════════════════════════════
# MAIN TABS
# ═══════════════════════════════════════════════
tab_build, tab_upgrade, tab_recommend, tab_compare = st.tabs(
    ["🏗️ Build a Deck", "🔧 Upgrade My Deck", "🧭 Commander Recommender", "⚔️ Compare Decks"])

# ── TAB 1: BUILD A DECK ──
with tab_build:
    # Config panel
    if st.session_state.show_config and st.session_state.selected_card:
        card = st.session_state.selected_card
        st.markdown("## ⚔️ Build Around This Card")
        cc1, cc2 = st.columns([1, 2])
        with cc1:
            if card["image_url"]: st.image(card["image_url"], use_container_width=True)
        with cc2:
            st.markdown(f"### {card['name']}")
            st.markdown(f"**{card['type_line']}**")
            st.markdown(f"**Colors:** {card['color_symbols']}")
            if card["oracle_text"]: st.caption(card["oracle_text"][:300])
            st.markdown("---")
            cfg_fmt = st.selectbox("📜 Format", ["Commander","Modern","Standard","Pioneer","Pauper"],
                key="cfg_fmt")
            cfg_strat = st.selectbox("🎯 Strategy", ["Aggressive","Midrange","Control","Combo"],
                key="cfg_strat")
            bc, cc = st.columns(2)
            with bc:
                if st.button("🚀 Build This Deck!", key="cfg_build", use_container_width=True):
                    st.session_state.show_config = False
                    st.session_state.deck_result = None
                    run_deck_build(selected_card=card, format_override=cfg_fmt,
                        strategy_override=cfg_strat)
            with cc:
                if st.button("❌ Cancel", key="cfg_cancel", use_container_width=True):
                    st.session_state.show_config = False
                    st.session_state.selected_card = None
                    st.rerun()
        st.markdown("---")

    # Custom build from sidebar
    if build_custom_button:
        if not creature_type.strip() and not color_identity:
            st.warning("⚠️ Enter a creature type or select colors!")
        else:
            st.session_state.deck_result = None
            st.session_state.show_config = False
            st.session_state.selected_card = None
            run_deck_build()

    # Show results
    if st.session_state.deck_result:
        st.markdown("---")
        st.markdown("## 📋 Your AI-Generated Deck")
        st.markdown(st.session_state.deck_result)

        # Save deck
        st.markdown("---")
        save_col1, save_col2 = st.columns([3, 1])
        with save_col1:
            save_name = st.text_input("Deck name:", placeholder="e.g., Dragon Commander", key="save_name")
        with save_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Save Deck", key="save_btn", use_container_width=True):
                if save_name:
                    st.session_state.saved_decks[save_name] = st.session_state.deck_result
                    st.success(f"Saved **{save_name}**!")
                else:
                    st.warning("Enter a deck name first.")

        # Analytics
        st.markdown("---")
        show_deck_analytics(st.session_state.deck_result)

        # Export
        st.markdown("---")
        show_export_options(st.session_state.deck_result)

        # Visual decklist
        show_visual_decklist(st.session_state.deck_result)

        # Swap tool
        st.markdown("---")
        show_swap_tool(st.session_state.deck_result)

        # Sideboard
        st.markdown("---")
        show_sideboard_gen(st.session_state.deck_result, format_choice_sidebar)

        # Matchups
        st.markdown("---")
        show_matchup_analysis(st.session_state.deck_result)

        # Download + Back
        st.markdown("---")
        dl_col, back_col = st.columns(2)
        with dl_col:
            st.download_button("📥 Download Decklist", data=st.session_state.deck_result,
                file_name="mtg_deck.txt", mime="text/plain", use_container_width=True)
        with back_col:
            if st.button("🏠 Back to Home", key="back_home", use_container_width=True):
                for k in ["deck_result","card_images","selected_card","deck_card_data",
                    "sideboard_result","matchup_result","swap_result"]:
                    st.session_state[k] = defaults[k]
                st.session_state.show_config = False
                st.rerun()

    # Home screen — Popular cards
    if st.session_state.deck_result is None and not st.session_state.show_config:
        st.markdown("## 🏆 Popular Commanders")
        plat_lbl = "🎮 Arena" if is_arena else "🃏 Paper"
        if color_identity:
            cmap = {"W":"⚪ White","U":"🔵 Blue","B":"⚫ Black","R":"🔴 Red","G":"🟢 Green"}
            st.caption(f"Colors: {', '.join(cmap[c] for c in selected_colors)} | {plat_lbl}")
        else:
            st.caption(f"All colors | {plat_lbl} | Select colors in sidebar to filter.")

        # Buttons row: Random Commander + Refresh Commanders
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
        with btn_col1:
            random_clicked = st.button("🎲 Random Commander", key="random_cmdr", use_container_width=True)
        with btn_col2:
            refresh_clicked = st.button("🔄 Refresh (AI Picks)", key="refresh_cmdr", use_container_width=True)

        # Handle Random Commander
        if random_clicked:
            try:
                resp = requests.get("https://api.scryfall.com/cards/random",
                    params={"q": "t:legendary t:creature f:commander"})
                if resp.status_code == 200:
                    rc = resp.json()
                    img = None
                    if "image_uris" in rc: img = rc["image_uris"].get("normal")
                    elif "card_faces" in rc and len(rc["card_faces"]) > 0:
                        if "image_uris" in rc["card_faces"][0]:
                            img = rc["card_faces"][0]["image_uris"].get("normal")
                    oracle = rc.get("oracle_text", "")
                    if not oracle and "card_faces" in rc:
                        oracle = " // ".join(f.get("oracle_text","") for f in rc["card_faces"])
                    ci = rc.get("color_identity", [])
                    cm = {"W":"⚪","U":"🔵","B":"⚫","R":"🔴","G":"🟢"}
                    cs = " ".join(cm.get(c,c) for c in ci) if ci else "Colorless"
                    st.session_state.selected_card = {
                        "name": rc.get("name",""), "mana_cost": rc.get("mana_cost",""),
                        "cmc": rc.get("cmc",0), "type_line": rc.get("type_line",""),
                        "oracle_text": oracle, "color_identity": ci, "color_symbols": cs,
                        "rarity": rc.get("rarity",""),
                        "price_usd": rc.get("prices",{}).get("usd","N/A"),
                        "image_url": img, "set_name": rc.get("set_name","")}
                    st.session_state.show_config = True
                    st.session_state.deck_result = None
                    st.rerun()
            except: st.error("Could not fetch random commander.")

        # Handle Refresh Commanders (AI curated)
        if refresh_clicked:
            with st.spinner("🤖 Claude is picking the best commanders for you... This takes ~15 seconds."):
                curated = fetch_curated_commanders(color_identity, is_arena)
            if curated:
                st.session_state.curated_commanders = curated
                st.rerun()
            else:
                st.warning("Could not fetch AI-curated commanders. Showing defaults.")

        # Determine which commanders to show
        if st.session_state.curated_commanders:
            display_commanders = st.session_state.curated_commanders
            st.success("🤖 **AI-Curated Picks** — Claude selected these based on current meta and popularity.")
        else:
            with st.spinner("Loading popular cards..."):
                display_commanders = fetch_popular_cards(color_identity, is_arena)

        if display_commanders:
            st.markdown("**👆 Click any card to build a deck — choose any format!**")
            cols = st.columns(4)
            for idx, card in enumerate(display_commanders):
                with cols[idx % 4]:
                    if card["image_url"]: st.image(card["image_url"], use_container_width=True)
                    st.markdown(f"**{card['name']}**")
                    st.caption(f"{card['color_symbols']} · {card['type_line']}")
                    if st.button("⚔️ Build Deck", key=f"pop_{idx}"):
                        st.session_state.selected_card = card
                        st.session_state.show_config = True
                        st.session_state.deck_result = None
                        st.rerun()
        else:
            st.warning("No cards found. Try different colors or platform.")

# ── TAB 2: UPGRADE MY DECK ──
with tab_upgrade:
    st.markdown("## 🔧 Upgrade My Deck")
    st.caption("Paste your existing decklist and let Claude suggest upgrades.")

    up_deck = st.text_area("Paste your decklist here:", height=300, key="up_deck",
        placeholder="1x Sol Ring\n1x Command Tower\n1x Lightning Bolt\n...")
    up_col1, up_col2 = st.columns(2)
    with up_col1:
        up_format = st.selectbox("Format:", ["Commander","Modern","Standard","Pioneer","Pauper"],
            key="up_fmt")
    with up_col2:
        up_budget = st.selectbox("Budget for upgrades:",
            ["No Limit","Budget ($50 or less)","Mid-range ($50–$150)"], key="up_budget")

    if st.button("🔧 Suggest Upgrades", key="up_btn", use_container_width=True):
        if up_deck.strip():
            prompt = (f"Here is my {up_format} decklist:\n\n{up_deck}\n\n"
                f"Budget for upgrades: {up_budget}\n\n"
                "Analyze this deck and provide:\n\n"
                "## 📈 Overall Assessment\n[Rate the deck 1-10 and explain strengths/weaknesses]\n\n"
                "## ❌ Cards to Cut (with reasons)\n- [Card] — reason to cut\n\n"
                "## ✅ Cards to Add (with reasons)\n- [Card] (~$X) — why it's an upgrade\n\n"
                "## 🔄 Suggested Swaps\n- [Old Card] → [New Card] — explanation\n\n"
                "## 💡 General Tips\n- Tips to improve the deck strategy")
            with st.spinner("Claude is analyzing your deck..."):
                result = call_claude("You are an expert MTG deck optimizer.", prompt, 3000)
            if result:
                st.session_state.upgrade_result = result
        else:
            st.warning("Paste a decklist first!")

    if st.session_state.upgrade_result:
        st.markdown("---")
        st.markdown(st.session_state.upgrade_result)

# ── TAB 3: COMMANDER RECOMMENDER ──
with tab_recommend:
    st.markdown("## 🧭 Commander Recommender")
    st.caption("Describe what you want to do and Claude will suggest the best commanders.")

    rec_desc = st.text_area("What do you want your deck to do?", height=100, key="rec_desc",
        placeholder="e.g., I want to make infinite tokens, steal my opponents' stuff, "
            "play big sea creatures, burn everything, mill everyone out...")

    rec_col1, rec_col2 = st.columns(2)
    with rec_col1:
        rec_budget = st.selectbox("Budget:", ["No Limit","Budget","Mid-range"], key="rec_budget")
    with rec_col2:
        rec_colors = st.text_input("Preferred colors (optional):",
            placeholder="e.g., Red Blue, or leave blank", key="rec_colors")

    if st.button("🧭 Recommend Commanders", key="rec_btn", use_container_width=True):
        if rec_desc.strip():
            color_note = f"\nPreferred colors: {rec_colors}" if rec_colors.strip() else ""
            prompt = (f"I want a Commander deck that: {rec_desc}\n"
                f"Budget: {rec_budget}{color_note}\n\n"
                "Recommend exactly 5 commanders. For each:\n\n"
                "## [Number]. [Commander Name]\n"
                "**Colors:** [color identity]\n"
                "**Strategy:** [1 sentence]\n"
                "**Why this commander:** [2-3 sentences]\n"
                "**Key cards to include:** [5 card names]\n"
                "**Budget-friendly?** [Yes/No + note]\n\n")
            with st.spinner("Finding the best commanders..."):
                result = call_claude("You are an expert MTG Commander specialist.", prompt, 2500)
            if result:
                st.session_state.recommend_result = result
        else:
            st.warning("Describe what you want your deck to do!")

    if st.session_state.recommend_result:
        st.markdown("---")
        st.markdown(st.session_state.recommend_result)

        # Try to show commander images
        names = re.findall(r'##\s*\d+\.\s*(.+)', st.session_state.recommend_result)
        if names:
            st.markdown("### 🖼️ Recommended Commanders")
            img_cols = st.columns(min(len(names), 5))
            for i, name in enumerate(names[:5]):
                clean = name.strip().rstrip("*").strip()
                try:
                    resp = requests.get("https://api.scryfall.com/cards/named",
                        params={"fuzzy": clean})
                    if resp.status_code == 200:
                        card = resp.json()
                        img = None
                        if "image_uris" in card: img = card["image_uris"].get("normal")
                        elif "card_faces" in card and len(card["card_faces"]) > 0:
                            if "image_uris" in card["card_faces"][0]:
                                img = card["card_faces"][0]["image_uris"].get("normal")
                        if img:
                            with img_cols[i]:
                                st.image(img, caption=clean, use_container_width=True)
                    time.sleep(0.1)
                except: pass

# ── TAB 4: COMPARE DECKS ──
with tab_compare:
    st.markdown("## ⚔️ Compare Two Decks")
    st.caption("Paste two decklists side by side to compare stats.")

    comp1, comp2 = st.columns(2)
    with comp1:
        deck1_text = st.text_area("Deck 1:", height=250, key="comp_deck1",
            placeholder="Paste first decklist...")
        deck1_name = st.text_input("Deck 1 Name:", value="Deck 1", key="comp_name1")
    with comp2:
        deck2_text = st.text_area("Deck 2:", height=250, key="comp_deck2",
            placeholder="Paste second decklist...")
        deck2_name = st.text_input("Deck 2 Name:", value="Deck 2", key="comp_name2")

    if st.button("📊 Compare Decks", key="comp_btn", use_container_width=True):
        if deck1_text.strip() and deck2_text.strip():
            parsed1 = parse_decklist(deck1_text)
            parsed2 = parse_decklist(deck2_text)

            if not parsed1 or not parsed2:
                st.warning("Could not parse one or both decklists.")
            else:
                with st.spinner("Fetching card data..."):
                    names1 = [c["name"] for c in parsed1]
                    names2 = [c["name"] for c in parsed2]
                    data1 = fetch_deck_cards(names1)
                    data2 = fetch_deck_cards(names2)

                st.markdown("---")

                # Price comparison
                st.markdown("### 💰 Price Comparison")
                price1 = sum(get_card_price(data1.get(c["name"].lower(), {})) * c["quantity"]
                    for c in parsed1)
                price2 = sum(get_card_price(data2.get(c["name"].lower(), {})) * c["quantity"]
                    for c in parsed2)
                pc1, pc2 = st.columns(2)
                pc1.metric(f"{deck1_name} Total", f"${price1:.2f}")
                pc2.metric(f"{deck2_name} Total", f"${price2:.2f}")

                # Card count
                st.markdown("### 📋 Card Counts")
                count1 = sum(c["quantity"] for c in parsed1)
                count2 = sum(c["quantity"] for c in parsed2)
                cc1, cc2 = st.columns(2)
                cc1.metric(f"{deck1_name} Cards", count1)
                cc2.metric(f"{deck2_name} Cards", count2)

                # Mana curves side by side
                st.markdown("### 📊 Mana Curves")
                mc1, mc2 = st.columns(2)

                for col, parsed, data, dname in [
                    (mc1, parsed1, data1, deck1_name),
                    (mc2, parsed2, data2, deck2_name)]:
                    cmc_counts = {i: 0 for i in range(8)}
                    for c in parsed:
                        d = data.get(c["name"].lower(), {})
                        tl = get_card_type(d).lower()
                        if "land" in tl: continue
                        bucket = min(int(get_card_cmc(d)), 7)
                        cmc_counts[bucket] += c["quantity"]
                    labels = ["0","1","2","3","4","5","6","7+"]
                    values = [cmc_counts[i] for i in range(8)]
                    fig = go.Figure(go.Bar(x=labels, y=values, marker_color="#6C3483",
                        text=values, textposition="auto"))
                    fig.update_layout(title=dname, height=300,
                        margin=dict(l=20,r=20,t=40,b=40))
                    with col:
                        st.plotly_chart(fig, use_container_width=True)

                # Color pies side by side
                st.markdown("### 🎨 Color Breakdown")
                cp1, cp2 = st.columns(2)
                pie_colors = {"White":"#F9FAF4","Blue":"#0E68AB","Black":"#150B00",
                    "Red":"#D3202A","Green":"#00733E","Colorless":"#CDC5BF","Multicolor":"#CFB53B"}
                cmf = {"W":"White","U":"Blue","B":"Black","R":"Red","G":"Green"}

                for col, parsed, data, dname in [
                    (cp1, parsed1, data1, deck1_name),
                    (cp2, parsed2, data2, deck2_name)]:
                    cc = {"White":0,"Blue":0,"Black":0,"Red":0,"Green":0,"Colorless":0,"Multicolor":0}
                    for c in parsed:
                        d = data.get(c["name"].lower(), {})
                        tl = get_card_type(d).lower()
                        if "land" in tl: continue
                        colors = get_card_colors(d)
                        if len(colors) > 1: cc["Multicolor"] += c["quantity"]
                        elif len(colors) == 1: cc[cmf.get(colors[0],"Colorless")] += c["quantity"]
                        else: cc["Colorless"] += c["quantity"]
                    filt = {k:v for k,v in cc.items() if v > 0}
                    if filt:
                        fig = go.Figure(go.Pie(labels=list(filt.keys()),
                            values=list(filt.values()),
                            marker=dict(colors=[pie_colors[k] for k in filt.keys()]),
                            hole=0.3))
                        fig.update_layout(title=dname, height=300,
                            margin=dict(l=20,r=20,t=40,b=20))
                        with col:
                            st.plotly_chart(fig, use_container_width=True)

                # Shared cards
                st.markdown("### 🤝 Shared Cards")
                names1_set = set(c["name"].lower() for c in parsed1)
                names2_set = set(c["name"].lower() for c in parsed2)
                shared = names1_set & names2_set
                if shared:
                    st.write(f"**{len(shared)} cards** in common:")
                    st.write(", ".join(sorted(n.title() for n in shared)))
                else:
                    st.write("No cards in common.")
        else:
            st.warning("Paste both decklists to compare!")

# ═══════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#888;font-size:0.85rem;">
    <p>⚡ Powered by <b>Scryfall API</b> + <b>Anthropic Claude</b> + <b>Streamlit</b> + <b>Plotly</b></p>
    <p>🔑 Requires an Anthropic API key →
    <a href="https://console.anthropic.com/" target="_blank">console.anthropic.com</a></p>
    <p>Card data © Wizards of the Coast. Images courtesy of Scryfall.</p>
</div>
""", unsafe_allow_html=True)
