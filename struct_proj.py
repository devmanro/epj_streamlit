
#wsl deb launching app.
# pyenv activate epj

# cd /mnt/e/shared_btw_linux_win/workspace/EPJ/epj_workstation/EPJ_PROJECT/logistics_app

#------------  ------------------------------------------------------------------------

# over here its just a script for making the project structure
import os
from pathlib import Path

def create_structure():
    # Define the base directory
    base_dir = Path("logistics_app")

    # Define the folder structure
    folders = [
        "data/archive",
        "reports",
        "modules",
        "assets"
    ]

    # Define initial files to create
    files = [
        "main.py",
        "requirements.txt",
        "modules/__init__.py",
        "modules/processor.py",
        "modules/reporter.py",
        "README.md"
    ]

    # Create Folders
    for folder in folders:
        os.makedirs(base_dir / folder, exist_ok=True)
        print(f"Created folder: {base_dir / folder}")

    # Create Files
    for file_path in files:
        file = base_dir / file_path
        if not file.exists():
            file.touch()
            print(f"Created file: {base_dir / file_path}")

    # Populate requirements.txt with your core libraries
    req_path = base_dir / "requirements.txt"
    with open(req_path, "w") as f:
        f.write("streamlit\npandas\nopenpyxl\nplotly\n")

    print("\n✅ Project structure initialized successfully!")
    print("Next step: Navigate to 'logistics_app' and run 'pip install -r requirements.txt'")

if __name__ == "__main__":
    create_structure()