import streamlit as st
from showmain import show_main_app 
# ============================================
#           LOGIN FUNCTION
# ============================================
def check_credentials(username, password):
    """Check if username and password are correct"""
    # Define your users here
    USERS = {
        "admin": "admin123",
        "user1": "password1",
        "john": "john2024",
        "devmanro":"123456789SH",
    }
    if username in USERS and USERS[username] == password:
        return True
    return False

def show_login_page():
    """Show the login form"""
    
    st.title("🔐 Welcome to My App")
    st.write("Please login to continue")
    st.divider()
    
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            st.subheader("Login")
            
            username = st.text_input(
                "👤 Username",
                placeholder="Enter username"
            )
            
            password = st.text_input(
                "🔑 Password",
                type="password",          # This hides the password
                placeholder="Enter password"
            )
            
            submit = st.form_submit_button(
                "Login",
                use_container_width=True
            )
            
            # When login button is clicked
            if submit:
                if not username or not password:
                    st.error("⚠️ Please fill in all fields")
                    
                elif check_credentials(username, password):
                    # Save login state
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success("✅ Login successful!")
                    st.rerun()  # Refresh the page
                    
                else:
                    st.error("❌ Wrong username or password")


# ============================================
#           APP ENTRY POINT
# ============================================
def main():
    # Initialize session state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    # ---- Show login or main app ----
    if not st.session_state.logged_in:
        show_login_page()   # Show login page
        st.stop()           # Don't show anything else
    else:
        show_main_app()     # Show your app

# Run the app
if __name__ == "__main__":
    main()
