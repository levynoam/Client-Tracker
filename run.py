"""Run the clinic clients app.

Usage:
    python run.py                                      # Use default: data/app.sqlite3
    DATABASE=./mydb.sqlite3 python run.py             # Custom database path
    python run.py --database ./custom/path.db         # Via command-line arg
"""
import os
import sys
from pathlib import Path
from app import create_app

# Support --database command-line argument
if "--database" in sys.argv:
    idx = sys.argv.index("--database")
    if idx + 1 < len(sys.argv):
        os.environ["DATABASE"] = sys.argv[idx + 1]
        sys.argv.pop(idx + 1)  # Remove the path
        sys.argv.pop(idx)      # Remove the flag

app = create_app()

if __name__ == "__main__":
    db_path = app.config["DATABASE"]
    print(f"Database: {db_path}", file=sys.stderr)
    app.run(host="0.0.0.0", port=5000, debug=True)
