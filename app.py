import streamlit as st
import pandas as pd
import json
import os
import re
from pathlib import Path
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Review Point Rating",
    layout="centered"
)

# --- Data Loading (Cached for Performance) ---
@st.cache_data
def load_data(data_folder):
    """
    Loads all necessary CSV and JSON files for the rating task.
    """
    try:
        user_df = pd.read_csv(Path(data_folder) / "user.csv")
        user_df.columns = user_df.columns.str.strip()
        with open(Path(data_folder) / "annotator_mapping.json", 'r', encoding='utf-8') as f:
            annotator_map = json.load(f)
        with open(Path(data_folder) / "combined_mapping.json", 'r', encoding='utf-8') as f:
            all_reviews = json.load(f)
        return user_df, annotator_map, all_reviews
    except FileNotFoundError as e:
        st.error(f"Error: A required data file was not found. Please check your './data' directory. Details: {e}")
        return None, None, None

# --- Review Parsing Function ---
def parse_review(review_text):
    """
    Parses a review string into a dictionary of sections and bullet points.
    """
    if not isinstance(review_text, str):
        return {"Summary": ["Not Available"], "Strengths": [], "Weaknesses": [], "Questions": []}

    sections = {"Summary": [], "Strengths": [], "Weaknesses": [], "Questions": []}
    summary_match = re.search(r'\*\*Summary\*\*(.*?)(?=\*\*Strengths\*\*|\Z)', review_text, re.DOTALL)
    strengths_match = re.search(r'\*\*Strengths\*\*(.*?)(?=\*\*Weaknesses\*\*|\Z)', review_text, re.DOTALL)
    weaknesses_match = re.search(r'\*\*Weaknesses\*\*(.*?)(?=\*\*Questions\*\*|\Z)', review_text, re.DOTALL)
    questions_match = re.search(r'\*\*Questions\*\*(.*)', review_text, re.DOTALL)

    if summary_match and summary_match.group(1).strip():
        sections["Summary"].append(summary_match.group(1).strip())

    for match, section_name in [(strengths_match, "Strengths"), (weaknesses_match, "Weaknesses"), (questions_match, "Questions")]:
        if match:
            content = match.group(1).strip()
            # Split by newline and hyphen, then clean up each point
            raw_points = content.split('\n-')
            cleaned_points = []
            for point in raw_points:
                cleaned = point.strip()
                # Remove a leading hyphen if it exists from the split
                if cleaned.startswith('-'):
                    cleaned = cleaned[1:].strip()
                # Only add non-empty points
                if cleaned:
                    cleaned_points.append(cleaned)
            sections[section_name] = cleaned_points
            
    return sections

# --- Display and Save Functions ---
def display_rating_form(review_data, review_key_prefix):
    """Displays a parsed review and inputs for four collective scores."""
    with st.container(border=True):
        if review_data.get("Summary"):
            st.markdown("**Summary**")
            st.markdown(review_data["Summary"][0])

        for section_name in ["Strengths", "Weaknesses", "Questions"]:
            if review_data.get(section_name):
                st.markdown(f"**{section_name}**")
                for point in review_data[section_name]:
                    st.markdown(f"- {point}")
        
        st.markdown("---")
        st.markdown("**Overall Rating**")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Reviewer Confidence", min_value=0.0, max_value=5.0, step=0.1, key=f"{review_key_prefix}_confidence")
            st.number_input("Constructiveness", min_value=0.0, max_value=5.0, step=0.1, key=f"{review_key_prefix}_constructiveness")
        with col2:
            st.number_input("Review Thoroughness", min_value=0.0, max_value=5.0, step=0.1, key=f"{review_key_prefix}_thoroughness")
            st.number_input("Helpfulness", min_value=0.0, max_value=5.0, step=0.1, key=f"{review_key_prefix}_helpfulness")


def save_results(results_path, record):
    """Saves a single evaluation record to a CSV file."""
    new_data = pd.DataFrame([record])
    if os.path.exists(results_path):
        results_df = pd.read_csv(results_path)
        combined_df = pd.concat([results_df, new_data], ignore_index=True)
    else:
        combined_df = new_data
    combined_df.to_csv(results_path, index=False)

def check_if_all_rated(review_key_prefix):
    """Validates that all four score inputs have non-zero values."""
    score_keys = [
        f"{review_key_prefix}_confidence",
        f"{review_key_prefix}_thoroughness",
        f"{review_key_prefix}_constructiveness",
        f"{review_key_prefix}_helpfulness"
    ]
    for key in score_keys:
        if st.session_state[key] == 0.0:
            return False
    return True

def get_user_progress(results_path, user):
    """Checks how many reviews a user has already completed."""
    if not os.path.exists(results_path):
        return 0
    try:
        results_df = pd.read_csv(results_path)
        if results_df.empty:
            return 0
        user_reviews = results_df[results_df['user'] == user]
        return len(user_reviews)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return 0
    except Exception:
        # In case of other errors reading the file, default to 0
        return 0

# --- Main Application ---
st.title("📝 Review Evaluation Task")

DATA_FOLDER = Path("./data")
RESULTS_CSV_PATH = DATA_FOLDER / 'evaluation_results.csv'

user_df, annotator_map, all_reviews = load_data(DATA_FOLDER)

if user_df is None:
    st.stop()

# --- User Login and Session State Initialization ---
st.sidebar.header("👤 Annotator Selection")
users = ["--- Select User ---"] + user_df['User'].tolist()
selected_user = st.sidebar.selectbox("Select your username:", users)

if selected_user != "--- Select User ---":
    # Initialize session state for the user
    if 'user' not in st.session_state or st.session_state.user != selected_user:
        st.session_state.user = selected_user
        
        # Check for previous progress
        completed_count = get_user_progress(RESULTS_CSV_PATH, selected_user)
        st.session_state.review_index = completed_count
        
        # Get the user's annotator ID
        annotator_id = user_df[user_df['User'] == selected_user]['annotator_id'].iloc[0]
        # Get the list of reviews assigned to this annotator
        st.session_state.review_queue = annotator_map.get(str(annotator_id), [])

    # --- Main Display Logic ---
    if not st.session_state.review_queue:
        st.warning("No reviews assigned to this user. Please check the mapping file.")
        st.stop()

    # Check if the user has completed all reviews
    if st.session_state.review_index >= len(st.session_state.review_queue):
        st.success("🎉 You have completed all your assigned reviews. Thank you!")
        st.balloons()
        st.stop()

    # Get the current review to display
    current_review_info = st.session_state.review_queue[st.session_state.review_index]
    paper_id, review_type = current_review_info
    
    review_text = all_reviews.get(paper_id, {}).get(review_type, f"Review for Paper ID {paper_id} and type {review_type} not found.")
    parsed_review = parse_review(review_text)

    st.header(f"Review {st.session_state.review_index + 1} of {len(st.session_state.review_queue)}")
    
    review_key_prefix = f"review_{st.session_state.review_index}"

    with st.form(key=f"rating_form_{st.session_state.review_index}"):
        display_rating_form(parsed_review, review_key_prefix)
        submitted = st.form_submit_button("Submit and Go to Next Review")

        if submitted:
            if not check_if_all_rated(review_key_prefix):
                st.error("Please enter a non-zero value for all four scores.")
            else:
                # Collect and save the single record
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "user": selected_user,
                    "paper_id": paper_id,
                    "review_type": review_type,
                    "reviewer_confidence": st.session_state[f"{review_key_prefix}_confidence"],
                    "review_thoroughness": st.session_state[f"{review_key_prefix}_thoroughness"],
                    "constructiveness": st.session_state[f"{review_key_prefix}_constructiveness"],
                    "helpfulness": st.session_state[f"{review_key_prefix}_helpfulness"],
                }
                
                save_results(RESULTS_CSV_PATH, record)
                st.toast("Rating submitted!", icon="✅")
                
                # Advance to the next review
                st.session_state.review_index += 1
                st.rerun()

else:
    st.info("Please select a user from the sidebar to begin.")

