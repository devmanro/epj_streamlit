import streamlit.web.cli as stcli
import os
import sys

if __name__ == "__main__":
    sys.argv = [
        "streamlit",
        "run",
        os.path.join(os.path.dirname(__file__), "main.py"),
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())

