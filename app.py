import streamlit as st
import svu_picker as picker

st.set_page_config(page_title="SVU Episode Picker", page_icon="🎬", layout="wide")

st.title("🎬 SVU Episode Picker")
st.markdown("""

### About this tool

This tool was developed by **Brittany Gonzales**. It recommends *Law & Order: SVU* episodes based on the most important factors:

1. **Stabler is still in the picture**
2. **IMDb rating is over 8.0** *(this can be adjusted)*
3. **Dr. Huang is featured**
4. **Munch/Finn are not heavily featured**
5. **No courtroom procedural episodes**


**How to use:**
- Pick your season + episode range in the sidebar 👈  
- Choose how many recommendations you want  
- Click **Get Recommendations** ✨  

""")
st.caption("Powered by your existing svu_picker.py logic + your episodes_picker.csv dataset.")

# ---- Load data ----
@st.cache_data
def load_data(csv_path: str):
    return picker.load_csv(csv_path)

with st.sidebar:
    st.header("Settings")

    csv_path = st.text_input("CSV file path", value="episodes_picker.csv")
    num_results = st.slider("How many recommendations?", min_value=1, max_value=20, value=5)

    col1, col2 = st.columns(2)
    with col1:
        start_season = st.number_input("Start season", min_value=1, max_value=30, value=3, step=1)
        start_episode = st.number_input("Start episode", min_value=1, max_value=50, value=1, step=1)
    with col2:
        end_season = st.number_input("End season", min_value=1, max_value=30, value=8, step=1)
        end_episode = st.number_input("End episode", min_value=1, max_value=50, value=22, step=1)

    exclude_seasons_text = st.text_input("Exclude seasons (comma-separated)", value="")

    st.divider()
    st.markdown("**Advanced (optional)**")
    min_rating = st.slider("Minimum IMDb rating", min_value=0.0, max_value=10.0, value=float(picker.MIN_IMDB_RATING), step=0.1)

    run_btn = st.button("✨ Get Recommendations", type="primary")

    reset_btn = st.button("↩️ Reset to defaults")
    if reset_btn:
        st.session_state.clear()
        st.rerun()

# ---- Main logic ----
if run_btn:
    try:
        episodes = load_data(csv_path)
    except FileNotFoundError:
        st.error(f"Couldn't find CSV at: {csv_path}\n\nMake sure it's on your Desktop or update the path.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        st.stop()

    range_str = f"S{int(start_season)}E{int(start_episode)}>S{int(end_season)}E{int(end_episode)}"
    try:
        rng = picker.parse_range(range_str)
    except Exception as e:
        st.error(f"Invalid range: {range_str}\n\n{e}")
        st.stop()

    exclude_seasons = []
    if exclude_seasons_text.strip():
        exclude_seasons = [
            int(x.strip())
            for x in exclude_seasons_text.split(",")
            if x.strip().isdigit()
        ]

    candidates = picker.filter_episodes(
        episodes,
        rng,
        min_imdb=min_rating,
        allow_seasons=picker.MAX_SEASONS_ALLOWED,
        exclude_seasons=exclude_seasons,
    )

    if not candidates:
        st.warning(
            "No episodes matched your constraints in that range.\n\n"
            "Try lowering the minimum IMDb rating, widening the range, or removing exclusions."
        )
        st.stop()

    results = picker.rank_and_select(candidates, n=num_results)

    st.subheader(f"Results ({len(results)})")
    st.write(f"Range: `{range_str}`")

    # Show results as nice “cards”
    for ep in results:
        with st.container(border=True):
            st.markdown(f"### {ep['title']}")
            st.markdown(f"**S{ep['season']}E{ep['episode']}** • **Air date:** {ep['air_date']} • **IMDb:** {ep['imdb_rating']}")
            if ep.get("one_sentence_plot"):
                st.markdown(f"**Plot:** {ep['one_sentence_plot']}")
            if ep.get("one_sentence_reason"):
                st.markdown(f"**Why it’s a great pick:** {ep['one_sentence_reason']}")

    st.divider()

    # Details view
    st.subheader("🔎 Details view")
    title_options = [ep["title"] for ep in results]
    selected_title = st.selectbox("Pick a recommended episode to expand", title_options)

    chosen = next((e for e in results if e["title"] == selected_title), None)
    if chosen:
        # details_expand returns markdown-ish text; Streamlit can render it
        st.markdown(picker.details_expand(chosen))

else:
    st.info("Set your range + options on the left, then click **Get Recommendations** ✨")
